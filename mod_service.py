from .setup import *  # noqa: F401,F403

name = 'service'


class ModuleService(PluginModuleBase):
    def __init__(self, P):
        super(ModuleService, self).__init__(P, name=name, first_menu='home')

    def process_menu(self, page, req):
        try:
            return render_template(f'{__package__}_{name}_home.html', services=self.P.service_manager.list_status())
        except Exception as e:
            self.P.logger.error(f'Exception:{str(e)}')
            self.P.logger.error(traceback.format_exc())
            return render_template('sample.html', title=f'{__package__}/{name}/{page}')

    def process_command(self, command, arg1, arg2, arg3, req):
        if command != 'restart':
            return jsonify({'ok': False, 'error': 'unknown command'}), 400
        result = self.P.service_manager.restart(arg1 or '', arg2 or '')
        return jsonify(result), (200 if result.get('ok') else 400)
