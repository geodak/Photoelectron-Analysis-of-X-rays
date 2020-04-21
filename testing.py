"""
Module for testing new ideas
"""

import numpy as np
import matplotlib.pyplot as plt 
from sklearn.metrics import mean_squared_error
from joblib import Parallel, delayed

import LRDeconvolve
from pax_simulations import run_analyze_save_load
from pax_simulations import simulate_pax
from visualize import plot_photoemission, plot_result, cv_plot
import assess_convergence

PARAMETERS = {
    'energy_loss': np.arange(-8, 10, 0.005),
    'iterations': int(1E1),
    'simulations': int(1E3),
    'cv_fold': 3,
    'regularizer_widths': np.logspace(-3, -1, 10)
}

TOTAL_SEPARATION_LIST = [0.05, 0.1, 0.15, 0.2, 0.25]
TOTAL_LOG10_NUM_ELECTRONS_LIST = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0]

def run_test(log10_num_electrons=10, rixs='schlappa', photoemission='ag'):
    data = run_analyze_save_load.run(log10_num_electrons, rixs, photoemission, **PARAMETERS)
    plot_photoemission.make_plot(data['deconvolver'])
    cv_plot.make_plot(data['deconvolver'])
    plot_result.make_plot(data['deconvolver'])

def convergence_test2(log10_num_electrons=4, rixs='schlappa', photoemission='ag', iterations=1E3):
    assess_convergence.run_pax_preset(log10_num_electrons, rixs, photoemission)

def run_cv_analysis(iterations=1E5):
    #points = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0]
    points = [6.0]
    for log10_num_electrons in points:
        run_analyze_save_load.run(log10_num_electrons, rixs=['doublet', 0.01], photoemission='fermi', **PARAMETERS)

def run_doublet_fermi_analysis():
    for separation in TOTAL_SEPARATION_LIST:
        for log10_num_electrons in TOTAL_LOG10_NUM_ELECTRONS_LIST:
            _ = run_analyze_save_load.run(log10_num_electrons, rixs=['doublet', separation], photoemission='fermi', **PARAMETERS)
