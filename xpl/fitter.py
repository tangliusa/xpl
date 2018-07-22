"""Provides functions for data processing."""
# pylint: disable=invalid-name
# pylint: disable=protected-access
# pylint: disable=logging-format-interpolation

import logging

# import numpy as np
from lmfit import Parameters
from lmfit.models import PseudoVoigtModel


logger = logging.getLogger(__name__)


class RegionFitModelIface(object):
    """This manages the Peak models and does the fitting."""
    # pylint: disable=invalid-name
    def __init__(self, region):
        self._single_models = {}
        self._params = Parameters()
        self._region = region

    @property
    def _total_model(self):
        """Returns the sum of all models."""
        if not self._single_models:
            return None
        model_list = list(self._single_models.values())
        model_sum = model_list[0]
        for i in range(1, len(model_list)):
            model_sum += model_list[i]
        return model_sum

    def add_peak(self, peak):
        """Adds a new Peak to the Model list."""
        if peak.region is not self._region:
            logger.error("peak with ID {} does not belong to region ID {}"
                         "".format(peak.ID, self._region.ID))
            raise ValueError("Peak does not belong to Region")

        if peak.model_name == "PseudoVoigt":
            model = PseudoVoigtModel(prefix=peak.prefix)
            model.set_param_hint("sigma", value=2, min=1e-5, max=5)
            model.set_param_hint("amplitude", value=2000, min=0)
            model.set_param_hint("fraction", vary=False)
        else:
            raise NotImplementedError("Only PseudoVoigt models supported")
        self._single_models[peak.prefix] = model

    def remove_peak(self, peak):
        """Removes a Peak from the model and instantiates a new
        CompositeModel."""
        if peak.prefix not in self._single_models:
            logger.error("peak {} not in model of region {}"
                         "".format(peak.ID, self._region.ID))
            raise AttributeError("Peak not in model")
        self._single_models.pop(peak.prefix)
        pars_to_del = [par for par in self._params if peak.prefix in par]
        for par in pars_to_del:
            self._params.pop(par)

    def init_params(self, peak, **kwargs):
        """Sets initial values chosen by user."""
        if peak.prefix not in self._params:
            self.add_peak(peak)
        for parname in ("area", "fwhm", "center"):
            if parname not in kwargs:
                logger.error("Missing parameter {}".format(parname))
                raise TypeError("Missing parameter {}".format(parname))

        model = self._single_models[peak.prefix]
        if peak.model_name == "PseudoVoigt":
            sigma = kwargs["fwhm"] / 2
            model.set_param_hint("sigma", value=sigma)
            model.set_param_hint("amplitude", value=kwargs["area"])
            model.set_param_hint("center", value=kwargs["center"])
            params = model.make_params()
            self._params += params
        else:
            raise NotImplementedError("Only PseudoVoigt models supported")

    def guess_params(self, peak):
        """Guesses parameters for a new peak."""
        if peak.prefix not in self._single_models:
            self.add_peak(peak)
        model = self._single_models[peak.prefix]
        other_models_cps = [0] * len(self._region.energy)
        for other_peak in self._region.peaks:
            if other_peak == peak:
                continue
            other_models_cps += self.get_peak_cps(other_peak)
        y = self._region.cps - self._region.background - other_models_cps
        params = model.guess(y, x=self._region.energy)
        self._params += params

    def fit(self):
        """Returns the fitted cps values."""
        if not self._single_models:
            return
        y = (self._region.cps - self._region.background)
        result = self._total_model.fit(y, self._params, x=self._region.energy)
        self._params = result.params

        for peak in self._region.peaks:
            if peak.model_name == "PseudoVoigt":
                amp = self._params["{}amplitude".format(peak.prefix)].value
                sigma = self._params["{}sigma".format(peak.prefix)].value
                center = self._params["{}center".format(peak.prefix)].value
                peak.set_params_from_model(
                    fwhm=sigma * 2,
                    area=amp,
                    center=center
                )
            else:
                raise NotImplementedError("Only PseudoVoigt models supported")
        # print(result.fit_report())

    def get_peak_cps(self, peak):
        """Returns the model evaluation value for a given Peak."""
        if peak.prefix not in self._single_models:
            logger.error("peak {} not in model of region {}"
                         "".format(peak.ID, self._region.ID))
            raise AttributeError("Peak not in model")
        model = self._single_models[peak.prefix]
        results = model.eval(params=self._params, x=self._region.energy)
        return results

    def get_cps(self):
        """Returns overall fit result."""
        if not self._total_model:
            return [0] * len(self._region.energy)
        results = self._total_model.eval(
            params=self._params,
            x=self._region.energy
        )
        return results

    # pylint: disable=too-many-arguments
    def add_constraint(self, peak, attr, min_=None, max_=None, vary=None,
                       expr=None, value=None):
        """Adds a constraint to a Peak parameter."""
        if peak.model_name == "PseudoVoigt":
            names = {
                "area": "amplitude",
                "fwhm": "sigma",
                "center": "center"}
            if attr == "fwhm":
                if min_:
                    min_ /= 2
                if max_:
                    max_ /= 2
                if value:
                    value /= 2
                if expr:
                    expr += "/ 2"
        else:
            raise NotImplementedError("Only PseudoVoigt models supported")
        paramname = "{}{}".format(peak.prefix, names[attr])
        self._params[paramname].set(
            min=min_,
            max=max_,
            vary=vary,
            expr=expr,
            value=value
        )

    def get_constraint(self, peak, attr, argname):
        """Returns a string containing min/max or expr."""
        if peak.model_name == "PseudoVoigt":
            names = {
                "area": "amplitude",
                "fwhm": "sigma",
                "center": "center"}
        else:
            raise NotImplementedError("Only PseudoVoigt models supported")
        paramname = "{}{}".format(peak.prefix, names[attr])
        min_ = self._params[paramname].min
        max_ = self._params[paramname].max
        _vary = self._params[paramname].vary
        expr = self._params[paramname].expr
        if attr == "fwhm":
            min_ *= 2
            max_ *= 2
            if expr:
                if expr[-3:] == "/ 2":
                    expr = expr[:-3]
        if argname == "min":
            return min_
        if argname == "max":
            return max_
        if argname == "expr":
            if expr is None:
                return ""
            return expr
        return None