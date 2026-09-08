"""The model suite. Imports are lazy (PEP 562) so a process that needs only
one member loads only that member's library: the N-BEATS child process must
not load LightGBM's OpenMP runtime before PyTorch starts its own."""
from importlib import import_module

_WHERE = {  # public name -> (module, attribute)
    "Forecaster": (".base", "Forecaster"), "SeasonalLevel": (".baseline", "SeasonalLevel"),
    "LightGBMForecaster": (".gbdt", "LightGBMForecaster"), "CatBoostForecaster": (".gbdt", "CatBoostForecaster"),
    "gbdt_available": (".gbdt", "available"),
    "NBeatsForecaster": (".nbeats", "NBeatsForecaster"), "nbeats_available": (".nbeats", "available"),
    "run_isolated": (".nbeats", "run_isolated"),
    "blend_weights": (".ensemble", "blend_weights"), "blend": (".ensemble", "blend"),
}
__all__ = list(_WHERE)


def __getattr__(name):
    if name in _WHERE:
        mod, attr = _WHERE[name]
        return getattr(import_module(mod, __name__), attr)
    raise AttributeError(name)
