"""
Lucy-Richardson deconvolution and variants
"""

import numpy as np
import tensorflow as tf
from sklearn.base import BaseEstimator
from sklearn.metrics import mean_squared_error
from scipy.signal import convolve
from sklearn.model_selection import GridSearchCV

import deconvolution_metrics

class LRFisterGrid(BaseEstimator):
    def __init__(self, impulse_response_x, impulse_response_y, convolved_x, regularizer_widths=[0.01, 0.1], iterations=1E3, ground_truth_y=None):
        self.impulse_response_x = impulse_response_x
        self.impulse_response_y = impulse_response_y
        self.convolved_x = convolved_x
        self.reconvolved_x = convolved_x
        self.deconvolved_x = self._get_deconvolved_x()
        self.regularizer_widths = regularizer_widths
        self.iterations = int(iterations)
        self.ground_truth_y = ground_truth_y

    def fit(self, X):
        deconvolver = LRFisterDeconvolve(
            self.impulse_response_x,
            self.impulse_response_y,
            self.convolved_x,
            iterations=self.iterations,
            ground_truth_y=self.ground_truth_y,
            logging=False
        )
        param_grid = {'regularizer_width': self.regularizer_widths}
        if self.ground_truth_y is not None:
            scoring = {
                'deconvolved': deconvolution_metrics.neg_deconvolved_mse,
                'reconvolved': deconvolution_metrics.neg_reconvolved_mse}
        else:
            scoring = {'reconvolved': deconvolution_metrics.neg_reconvolved_mse}
        deconvolver_gs = GridSearchCV(
            deconvolver,
            param_grid,
            cv=5,
            return_train_score=True,
            verbose=True,
            scoring=scoring,
            refit='reconvolved',
            n_jobs=-1
        )
        deconvolver_gs.fit(X)
        self.measured_y_ = np.mean(X, axis=0)
        self.deconvolved_y_ = deconvolver_gs.best_estimator_.deconvolved_y_
        self.reconvolved_y_ = convolve(self.deconvolved_y_, self.impulse_response_y, mode='valid')
        self.gridsearch_cv_results_ = deconvolver_gs.cv_results_
        self.deconvolved_mse_ = -1*deconvolver_gs.cv_results_['mean_test_deconvolved']
        self.deconvolved_mse_std_ = deconvolver_gs.cv_results_['std_test_deconvolved']
        self.reconvolved_mse_ = -1*deconvolver_gs.cv_results_['mean_train_reconvolved']
        self.reconvolved_mse_std_ = deconvolver_gs.cv_results_['std_train_reconvolved']
        self.cv_ = -1*deconvolver_gs.cv_results_['mean_test_reconvolved']
        self.cv_std_ = deconvolver_gs.cv_results_['std_test_reconvolved']
        return self

    def predict(self, X):
        return self.deconvolved_y_

    def _get_deconvolved_x(self):
        average_impulse_x = np.mean(self.impulse_response_x)
        deconvolved_x = self.convolved_x-average_impulse_x
        return deconvolved_x


class LRDeconvolve(BaseEstimator):
    def __init__(self, impulse_response_x, impulse_response_y, convolved_x, iterations=5, ground_truth_y=None):
        self.impulse_response_x = impulse_response_x
        self.impulse_response_y = impulse_response_y
        self.convolved_x = convolved_x
        self.reconvolved_x = convolved_x
        self.deconvolved_x = self._get_deconvolved_x()
        self.iterations = int(iterations)
        self.ground_truth_y = ground_truth_y

    def fit(self, X):
        """Perform PAX 
        parameters:
            X: array, rows are PAX spectra measurements, columns are specific electron energies
        """
        self.measured_y_ = np.mean(X, axis=0)
        self.deconvolved_y_ = self._LR(self.measured_y_)
        self.reconvolved_y_ = convolve(self.deconvolved_y_, self.impulse_response_y, mode='valid')
        return self

    def _LR(self, measured_y):
        """Perform Lucy-Richardson deconvolution of measured_y
        """
        previous_O = self._deconvolution_guess(measured_y)
        impulse_response_y_reversed = np.flip(self.impulse_response_y)
        writer = tf.summary.create_file_writer('logdir_test')
        with writer.as_default():
            for iteration in range(self.iterations):
                I = convolve(previous_O, self.impulse_response_y, mode='valid')
                relative_blur = measured_y/I
                correction_factor_estimate = convolve(relative_blur, impulse_response_y_reversed, mode='valid')
                current_O = previous_O*correction_factor_estimate
                previous_O = current_O
                self._save_iteration_stats(current_O, iteration)
                writer.flush()
        return current_O

    def _save_iteration_stats(self, current_deconvolved, iteration):
        current_reconstruction = convolve(current_deconvolved, self.impulse_response_y, mode='valid')
        reconstruction_mse = mean_squared_error(current_reconstruction, self.measured_y_)
        tf.summary.scalar('reconstruction_mse', reconstruction_mse, step=iteration)
        if self.ground_truth_y is not None:
            # We have access to the ground truth, so we can calculate a few more metrics
            deconvolved_mse = mean_squared_error(current_deconvolved, self.ground_truth_y)
            tf.summary.scalar('deconvolved_mse', deconvolved_mse, step=iteration)
            ground_truth_reconvolved = convolve(self.ground_truth_y, self.impulse_response_y, mode='valid')
            reconvolved_mse = mean_squared_error(current_reconstruction, ground_truth_reconvolved)
            tf.summary.scalar('reconvolved_mse', reconvolved_mse, step=iteration)


    def _deconvolution_guess(self, measured_y):
        """Return initial guess for deconvolved signal
        """
        sigma = 1
        x = self.impulse_response_x
        mu = np.mean(x)
        gauss = np.exp((-1/2)*((x-mu)/sigma)**2)
        gauss = gauss/np.sum(gauss)
        #return convolve(measured_y, gauss, mode='valid')
        return measured_y

    def predict(self, X):
        return self.deconvolved_y_
        
    def score(self, X_test):
        """Default scoring is reconvolved mean squared error
        """
        mean_X_test = np.mean(X_test, axis=0)
        mse = mean_squared_error(self.reconvolved_y_, mean_X_test)
        return -1*mse

    def _get_deconvolved_x(self):
        average_impulse_x = np.mean(self.impulse_response_x)
        deconvolved_x = self.convolved_x-average_impulse_x
        return deconvolved_x

class LRFisterDeconvolve(LRDeconvolve):
    """Lucy-Richardson deconvolution with Fister regularization
    """

    def __init__(self, impulse_response_x, impulse_response_y, convolved_x, regularizer_width=0.05, iterations=1E2, ground_truth_y=None, logging=False):
        self.impulse_response_x = impulse_response_x
        self.impulse_response_y = impulse_response_y
        self.convolved_x = convolved_x
        self.reconvolved_x = convolved_x
        self.deconvolved_x = self._get_deconvolved_x()
        self.regularizer_width = regularizer_width
        self.iterations = int(iterations)
        self.ground_truth_y = ground_truth_y
        self.logging = logging

    def _LR_fister(self, measured_y):
        """Perform Fister-regularized Lucy-Richardson deconvolution of measured_y
        """
        gauss = self._normalized_gaussian(
            self.impulse_response_x,
            np.mean(self.impulse_response_x),
            self.regularizer_width
        )
        previous_O = self._deconvolution_guess(measured_y)
        impulse_response_y_reversed = np.flip(self.impulse_response_y)
        if self.logging:
            writer = tf.summary.create_file_writer(f'logdir_test/{self.regularizer_width}')
            with writer.as_default():
                for iteration in range(self.iterations):
                    I = convolve(previous_O, self.impulse_response_y, mode='valid')
                    relative_blur = measured_y/I
                    correction_factor_estimate = convolve(relative_blur, impulse_response_y_reversed, mode='valid')
                    current_O = previous_O*correction_factor_estimate
                    current_O = convolve(current_O, gauss, mode='valid')
                    previous_O = current_O
                    self._save_iteration_stats(current_O, iteration)
                writer.flush()
        else:
            for iteration in range(self.iterations):
                I = convolve(previous_O, self.impulse_response_y, mode='valid')
                relative_blur = measured_y/I
                correction_factor_estimate = convolve(relative_blur, impulse_response_y_reversed, mode='valid')
                current_O = previous_O*correction_factor_estimate
                current_O = convolve(current_O, gauss, mode='valid')
                previous_O = current_O
        return current_O

    def _LR_fister_iteration(self, previous_deconvolved, measured_y, impulse_response_y_reversed, gauss):
        """Perform one iteration of Fister-regularized Lucy-Richardson deconvolution
        (currently unused)
        """
        I = convolve(previous_deconvolved, self.impulse_response_y, mode='valid')
        relative_blur = measured_y/I
        correction_factor_estimate = convolve(relative_blur, impulse_response_y_reversed, mode='valid')
        current_deconvolved = previous_deconvolved*correction_factor_estimate
        current_deconvolved = convolve(current_deconvolved, gauss, mode='valid')
        return current_deconvolved

    def fit(self, X):
        """Perform PAX 
        parameters:
            X: array, rows are PAX spectra measurements, columns are specific electron energies
        """
        self.measured_y_ = np.mean(X, axis=0)
        self.deconvolved_y_ = self._LR_fister(self.measured_y_)
        self.reconvolved_y_ = convolve(self.deconvolved_y_, self.impulse_response_y, mode='valid')
        return self

    def _normalized_gaussian(self, x, mu, sigma):
        """Return a normalized gaussian function 
        center: mu
        standard deviation: sigma
        unit integrated amplitude
        """
        norm_gauss = np.exp((-1/2)*((x-mu)/sigma)**2)
        norm_gauss = norm_gauss/np.sum(norm_gauss)
        return norm_gauss

class LRL2Deconvolve(LRDeconvolve):
    """Lucy-Richardson deconvolution with L2 regularization
    """

    def __init__(self, impulse_response_x, impulse_response_y, convolved_x, alpha=0.05, **kwargs):
        super().__init__(impulse_response_x, impulse_response_y, convolved_x, **kwargs)
        self.alpha = alpha

    def fit(self, X):
        """Perform PAX 
        parameters:
            X: array, rows are PAX spectra measurements, columns are specific electron energies
        """
        measured_y = np.mean(X, axis=0)
        self.deconvolved_y_ = self._LRL2(measured_y)
        self.reconvolved_y_ = convolve(self.deconvolved_y_, self.impulse_response_y, mode='valid')
        return self

    def _LRL2(self, measured_y):
        """Perform L2-regularized Lucy-Richardson deconvolution of measured_y
        """
        previous_O = self._deconvolution_guess(measured_y)
        impulse_response_y_reversed = np.flip(self.impulse_response_y)
        for _ in range(self.iterations):
            I = convolve(previous_O, self.impulse_response_y, mode='valid')
            relative_blur = measured_y/I
            correction_factor_estimate = convolve(relative_blur, impulse_response_y_reversed, mode='valid')
            current_O = previous_O*correction_factor_estimate
            current_O = (-1+np.sqrt(1+2*self.alpha*current_O))/self.alpha
            previous_O = current_O
        return current_O