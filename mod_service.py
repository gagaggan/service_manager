from .setup import *  # noqa: F401,F403

import json

name = 'service'


class ModuleService(PluginModuleBase):
    db_default = {
        'service_docker_containers': 'plex',
        'service_systemd_services': 'user|jmnoh|codex-app-server.service\nnginx.service\nplexmediaserver.service',
    }

    def __init__(self, P):
        super(ModuleService, self).__init__(P, name=name, first_menu='home')

    def process_menu(self, page, req):
        try:
            if page == 'setting':
                return render_template(f'{__package__}_{name}_setting.html', arg=self.P.ModelSetting.to_dict())
            return render_template(f'{__package__}_{name}_home.html', services=self.P.service_manager.list_status())
        except Exception as e:
            self.P.logger.error(f'Exception:{str(e)}')
            self.P.logger.error(traceback.format_exc())
            return render_template('sample.html', title=f'{__package__}/{name}/{page}')

    def process_command(self, command, arg1, arg2, arg3, req):
        if command not in ('start', 'stop', 'restart'):
            return jsonify({'ok': False, 'error': 'unknown command'}), 400
        result = self.P.service_manager.control(command, arg1 or '', arg2 or '')
        return jsonify(result), (200 if result.get('ok') else 400)

    def plugin_load(self):
        self.P.service_manager.configure_from_settings(self.P.ModelSetting)
        self.P.service_manager.sync_systemd_allowlist()

    def setting_save_after(self, change_list):
        self.P.service_manager.configure_from_settings(self.P.ModelSetting)
        self.P.service_manager.sync_systemd_allowlist()
