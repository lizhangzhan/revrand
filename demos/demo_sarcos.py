#! /usr/bin/env python3
""" A La Carte GP Application to SARCOS dataset. """

import os
import logging
import numpy as np
import computers.gp as gp

from pyalacarte import regression, basis_functions
from pyalacarte.validation import smse, msll
from pyalacarte.utils.datasets import fetch_gpml_sarcos_data

#
# Settings
#

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

lenscale = 10
sigma = 100
noise = 1
regulariser = 1
nbases = 500
gp_Ntrain = 1024
passes = 25
rate = 0.9
eta = 1e-6
batchsize = 100

useSGD = True
diagcov = True


#
# Load data
#

gpml_sarcos = fetch_gpml_sarcos_data()

X_train = gpml_sarcos.train.data
y_train = gpml_sarcos.train.targets

X_test = gpml_sarcos.test.data
y_test = gpml_sarcos.test.targets

Ntrain, D = X_train.shape


# Get random subset of data for training the GP
train_ind = np.random.choice(range(Ntrain), size=gp_Ntrain, replace=False)
X_train_sub = X_train[train_ind, :]
y_train_sub = y_train[train_ind]

#
# Train A la Carte
#

base = basis_functions.RandomRBF_ARD(nbases, D)
lenARD = lenscale * np.ones(D)

if useSGD:
    log.info("Using SGD regressor")
    params = regression.bayes_regress_sgd(X_train, y_train, base, [lenARD],
                                          rate=rate, var=noise**2,
                                          regulariser=regulariser, eta=eta,
                                          passes=passes, batchsize=batchsize)
else:
    log.info("Using full variational regressor")
    params = regression.bayes_regress(X_train, y_train, base, [lenARD],
                                      var=noise**2, diagcov=diagcov,
                                      regulariser=regulariser)

#
# Train GP
#

kdef = lambda h, k: h(1e-5, 1e5, sigma) \
    * k('gaussian', h(np.ones(D) * 1e-5, np.ones(D) * 1e5, lenARD))
kfunc = gp.compose(kdef)

# Set up optimisation
learning_params = gp.OptConfig()
learning_params.sigma = gp.auto_range(kdef)
learning_params.noise = gp.Range([1e-5], [1e5], [noise])
learning_params.walltime = 300


# Learn hyperparameters
hyper_params = gp.learn(X_train_sub, y_train_sub, kfunc, learning_params)
regressor = gp.condition(X_train_sub, y_train_sub, kfunc, hyper_params)


#
# Predict GP
#

query = gp.query(X_test, regressor)
Ey_gp = gp.mean(regressor, query)
Vf_gp = gp.variance(regressor, query) + np.array(hyper_params[1])**2
Vy_gp = Vf_gp + np.array(hyper_params[1])**2
Sy_gp = np.sqrt(Vy_gp)


#
# Predict A la Carte
#

Ey, Vf, Vy = regression.bayes_predict(X_test, base, *params)
Sy = np.sqrt(Vy)


#
# Validation
#

log.info("Subset GP smse = {}, msll = {},\n\thypers = {}, noise = {}."
         .format(smse(y_test, Ey_gp), msll(y_test, Ey_gp, Vy_gp, y_train),
                 hyper_params[0], hyper_params[1]))
log.info("A la Carte smse = {}, msll = {},\n\thypers = {}, noise = {}."
         .format(smse(y_test, Ey), msll(y_test, Ey, Vy, y_train),
                 params[2], np.sqrt(params[3])))