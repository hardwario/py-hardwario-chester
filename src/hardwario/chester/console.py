import threading
import os
import asyncio
import logging
from functools import partial
from datetime import datetime
from loguru import logger
from prompt_toolkit.eventloop.utils import get_event_loop
from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, VSplit, Window, WindowAlign
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.margins import NumberedMargin, ScrollbarMargin
from prompt_toolkit.widgets import SearchToolbar, TextArea, Frame, HorizontalLine
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.clipboard.pyperclip import PyperclipClipboard
from prompt_toolkit.application.current import get_app
from .nrfjprog import NRFJProg, NRFJProgRTTNoChannels


def getTime():
    return datetime.now().strftime('%Y.%m.%d %H:%M:%S.%f')[:23]


class Console:

    def __init__(self, history_file):

        shell_search = SearchToolbar(ignore_case=True, vi_mode=True)
        shell_window = TextArea(
            scrollbar=True,
            line_numbers=True,
            focusable=True,
            focus_on_click=True,
            read_only=True,
            search_field=shell_search
        )
        self.shell_buffer = shell_window.buffer

        logger_search = SearchToolbar(ignore_case=True, vi_mode=True)
        logger_window = TextArea(
            scrollbar=True,
            line_numbers=True,
            focusable=True,
            focus_on_click=True,
            read_only=True,
            search_field=logger_search
        )
        self.logger_buffer = logger_window.buffer

        logger.debug(f'history_file: {history_file}')

        os.makedirs(os.path.dirname(history_file), exist_ok=True)

        input_history = FileHistory(history_file)
        search_field = SearchToolbar(ignore_case=True)

        self.input_field = TextArea(
            height=1,
            prompt=">>> ",
            style="class:input-field",
            multiline=False,
            wrap_lines=False,
            search_field=search_field,
            history=input_history,
            focusable=True,
            focus_on_click=True)

        def get_titlebar_text():
            return [
                ("class:title", " HARDWARIO CHESTER Console "),
                ("class:title", " (Press [Ctrl-Q] to quit.)"),
            ]

        root_container = HSplit(
            [
                # The titlebar.
                Window(
                    height=1,
                    content=FormattedTextControl(get_titlebar_text),
                    align=WindowAlign.CENTER,
                ),
                VSplit(
                    [
                        Frame(HSplit(
                            [
                                shell_window,
                                shell_search,
                                HorizontalLine(),
                                self.input_field,
                                search_field
                            ]
                        ), title="Shell"),
                        Frame(HSplit(
                            [
                                logger_window,
                                logger_search
                            ]
                        ), title="Log"),
                    ]
                )
            ]
        )

        bindings = KeyBindings()

        @bindings.add("c-insert", eager=True)  # TODO: check
        @bindings.add("c-c", eager=True)
        def do_copy(event):
            if event.app.layout.has_focus(shell_window):
                data = shell_window.buffer.copy_selection()
                event.app.clipboard.set_data(data)

            elif event.app.layout.has_focus(logger_window):
                data = logger_window.buffer.copy_selection()
                event.app.clipboard.set_data(data)

        @ bindings.add("c-q", eager=True)
        def _(event):
            event.app.exit()

        bindings.add("tab")(focus_next)
        bindings.add("s-tab")(focus_previous)

        self.app = Application(
            layout=Layout(root_container, focused_element=self.input_field),
            key_bindings=bindings,
            mouse_support=True,
            full_screen=True,
            enable_page_navigation_bindings=True,
            clipboard=PyperclipClipboard()
        )

    def run(self, prog: NRFJProg, console_file):
        channels = prog.rtt_start()

        if 'Logger' not in channels:
            raise Exception('Not found RTT Logger channel')

        if 'Terminal' not in channels:
            raise Exception('Not found RTT Terminal channel')

        async def task_rtt_read(channel, buffer):
            while prog.rtt_is_running:
                with logger.catch(message='task_rtt_read', reraise=True):
                    try:
                        line = prog.rtt_read(channel)
                    except NRFJProgRTTNoChannels:
                        return
                    if line:
                        # buffer.insert_text(line.replace('\r', ''))
                        for sline in line.splitlines():
                            console_file.write(getTime() + (' # ' if channel == 'Logger' else ' > '))
                            console_file.write(sline)
                            console_file.write('\n')
                        console_file.flush()

                        line = line.replace('\r', '')
                        buffer.set_document(Document(buffer.text + line, None), True)
                    await asyncio.sleep(0.05)

        console_file.write(f'{ "*" * 80 }\n')

        async def task_rtt_read_logger():
            await task_rtt_read('Logger', self.logger_buffer)

        async def task_rtt_read_terminal():
            await task_rtt_read('Terminal', self.shell_buffer)

        loop = get_event_loop()
        loop.create_task(task_rtt_read_logger())
        loop.create_task(task_rtt_read_terminal())

        def accept(buff):
            line = f'{buff.text}\n'.replace('\r', '')
            # self.shell_buffer.insert_text(line)
            console_file.write(f'{getTime()} < {line}')
            text = self.shell_buffer.text + line
            self.shell_buffer.set_document(Document(text, None), True)

            prog.rtt_write('Terminal', f'{buff.text}\n')
            return None

        self.input_field.accept_handler = accept

        self.app.run()

        prog.rtt_stop()
