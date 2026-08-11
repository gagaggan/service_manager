"""FlaskFarm plugin entry point and framework-neutral factory."""

from .service_manager import ServiceManager


def create_manager(config=None):
    return ServiceManager(config)


try:
    # FlaskFarm's plugin loader imports create_plugin_instance from the plugin package.
    from flaskfarm.lib.plugin.create_plugin import PluginBase  # type: ignore
except ImportError:
    PluginBase = None


def create_plugin_instance(setting):
    """Compatibility hook; full menu adapter is added after version confirmation."""
    if PluginBase is None:
        return None
    return PluginBase(setting)

