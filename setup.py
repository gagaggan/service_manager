"""FlaskFarm plugin bootstrap, following the official plugin convention."""

from .service_manager import ServiceManager

__menu = {
    'uri': __package__, 'name': '서비스 관리',
    'list': [{'uri': 'service', 'name': 'Docker / systemd'}, {'uri': 'log', 'name': '로그'}],
}
setting = {
    'filepath': __file__, 'use_db': False, 'use_default_setting': False,
    'home_module': 'service', 'menu': __menu, 'setting_menu': None,
    'default_route': 'normal',
}

from plugin import *  # noqa: E402,F401,F403

P = create_plugin_instance(setting)
P.service_manager = ServiceManager({
    'docker': {'enabled': True, 'containers': ['codex', 'plex']},
    'systemd': {'enabled': True, 'services': ['nginx.service']},
})

from .mod_service import ModuleService  # noqa: E402
P.set_module_list([ModuleService])
