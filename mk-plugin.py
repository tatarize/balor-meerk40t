
def plugin(kernel, lifecycle):
    if lifecycle == 'register':
        """
        Register our changes to meerk40t. These should modify the registered values within meerk40t or install different
        modules and modifiers to be used in meerk40t.
        """
        def example():
            yield COMMAND_WAIT_FINISH
            def print_hello():
                print("Hello World.")
            yield COMMAND_FUNCTION, print_hello()
        kernel.register('plan/example', example)
        @kernel.console_command('example', help="Says Hello World.")
        def example_cmd(command, channel, _, args=tuple(), **kwargs):
            channel(_('Hello World'))
    elif lifecycle == 'boot':
        """
        Do some persistent actions or start modules and modifiers. Register any scheduled tasks or threads that need
        to be running for our plugin to work. 
        """
        pass
    elif lifecycle == 'ready':
        """
        Start process running. Sometimes not all modules and modifiers will be ready as they are processed in order
        during boot. If your thread or work depends on other parts of the system being fully established they should 
        work here.
        """
        pass
    elif lifecycle == 'mainloop':
        """
        This is the start of the gui and will capture the default thread as gui thread. If we are writing a new gui
        system and we need this thread to do our work. It should be captured here. This is the main work of the program. 
        """
        pass
    elif lifecycle == 'shutdown':
        """
        Meerk40t's closing down, our plugin should adjust accordingly. All registered meerk40t processes will be stopped
        any plugin processes should also be stopped so the program can close correctly.
        """
        pass
