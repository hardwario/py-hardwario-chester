import threading
import os
import asyncio
import logging
import sys
import re
from functools import partial
from datetime import datetime
from loguru import logger
from prompt_toolkit.eventloop.utils import get_event_loop
from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, VSplit, Window, WindowAlign, ConditionalContainer
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.margins import NumberedMargin, ScrollbarMargin
from prompt_toolkit.widgets import SearchToolbar, TextArea, Frame, HorizontalLine, Box, Label
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.clipboard.pyperclip import PyperclipClipboard
from prompt_toolkit.application.current import get_app
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.styles.named_colors import NAMED_COLORS
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout.dimension import LayoutDimension
from .nrfjprog import NRFJProg, NRFJProgRTTNoChannels, NRFJProgException


def get_time():
    return datetime.now().strftime('%Y.%m.%d %H:%M:%S.%f')[:23]


log_level_color_lut = {
    'X': NAMED_COLORS['Blue'],
    'D': NAMED_COLORS['Magenta'],
    'I': NAMED_COLORS['Green'],
    'W': NAMED_COLORS['Yellow'],
    'E': NAMED_COLORS['Red'],
    'dbg': NAMED_COLORS['Magenta'],
    'inf': NAMED_COLORS['Green'],
    'wrn': NAMED_COLORS['Yellow'],
    'err': NAMED_COLORS['Red'],
}


class LogLexer(Lexer):

    def __init__(self, patern, colors=log_level_color_lut) -> None:
        super().__init__()
        self.patern = patern
        self.colors = colors

    def lex_document(self, document):
        def get_line(lineno):
            line = document.lines[lineno]

            g = re.match(self.patern, line)
            if g:
                color = self.colors.get(g.group(2), '#ffffff')
                return [(color, g.group(1)), ('#ffffff', g.group(3))]

            return [('#ffffff', line)]

        return get_line


class Console:

    def __init__(self, prog: NRFJProg, history_file, console_file, latency=50):
        self.exception = None
        self.show_status_bar = True

        channels = prog.rtt_start()

        is_old = False

        if 'Terminal' not in channels:
            raise Exception('Not found RTT Terminal channel')

        if len(channels) > 1:
            if 'Logger' not in channels:
                raise Exception('Not found RTT Logger channel')
        elif len(channels) == 1:
            is_old = True

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
            search_field=logger_search,
            lexer=LogLexer(r'^(#.*?\d(?:\.\d+)? <(\w)\>)(.*)' if is_old else r'^(\[.*?\].*?<(\w+)\>)(.*)')
        )
        self.logger_buffer = logger_window.buffer
        logger.debug(f'history_file: {history_file}')

        os.makedirs(os.path.dirname(history_file), exist_ok=True)

        input_history = FileHistory(history_file)
        search_field = SearchToolbar(ignore_case=True)

        self.input_field = TextArea(
            height=1,
            prompt="Command: ",
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
                ("class:title", " (Press [Ctrl-Q] or [F4] to quit.)"),
            ]

        def get_statusbar_text():
            return " Press Ctrl-C to open menu. "

        def get_statusbar_time():
            return get_time()[:19]

        status_bar = ConditionalContainer(
            content=VSplit([
                Window(
                    FormattedTextControl(get_titlebar_text), style="class:status"
                ),
                Window(
                    FormattedTextControl(get_statusbar_time),
                    style="class:status.right",
                    width=24,
                    align=WindowAlign.RIGHT,
                ),
                Window(width=1, align=WindowAlign.RIGHT)
            ],
                height=LayoutDimension.exact(1),
                style="class:status",),
            filter=Condition(lambda: self.show_status_bar))

        root_container = HSplit(
            [
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
                        ), title="Interactive Shell"),
                        Frame(HSplit(
                            [
                                logger_window,
                                logger_search
                            ]
                        ), title="Device Log"),
                    ]
                ),
                status_bar
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

        @bindings.add("c-q", eager=True)
        @bindings.add("f4", eager=True)
        def _(event):
            event.app.exit()

        bindings.add("tab")(focus_next)
        bindings.add("s-tab")(focus_previous)

        self.app = Application(
            layout=Layout(root_container, focused_element=self.input_field),
            key_bindings=bindings,
            mouse_support=True,
            full_screen=True,
            refresh_interval=1,
            enable_page_navigation_bindings=True,
            clipboard=PyperclipClipboard()
        )

        rtt_read_delay = latency / 1000.0

        if is_old:
            async def task_rtt_read():
                while prog.rtt_is_running:
                    with logger.catch(message='task_rtt_read', reraise=True):
                        try:
                            lines = prog.rtt_read('Terminal')
                        except NRFJProgRTTNoChannels:
                            return
                        if lines:
                            shell = ''
                            log = ''
                            for line in lines.splitlines():
                                if line.startswith('#'):
                                    log += line + '\n'
                                    console_file.write(get_time() + ' ')
                                    console_file.write(line)
                                else:
                                    shell += line + '\n'
                                    console_file.write(get_time() + ' > ')
                                    console_file.write(line)
                                console_file.write('\n')
                            console_file.flush()

                            if shell:
                                shell = shell.replace('\r', '')
                                self.shell_buffer.set_document(Document(self.shell_buffer.text + shell, None), True)
                            if log:
                                log = log.replace('\r', '')
                                self.logger_buffer.set_document(Document(self.logger_buffer.text + log, None), True)

                        await asyncio.sleep(rtt_read_delay)

        else:
            channels_up = (('Terminal', self.shell_buffer), ('Logger', self.logger_buffer))

            async def task_rtt_read():
                while prog.rtt_is_running:
                    for channel, buffer in channels_up:
                        with logger.catch(message='task_rtt_read', reraise=True):
                            try:
                                line = prog.rtt_read(channel)
                            except NRFJProgRTTNoChannels:
                                return
                            except NRFJProgException as e:
                                self.exit(e)
                                return
                            if line:
                                # buffer.insert_text(line.replace('\r', ''))
                                for sline in line.splitlines():
                                    console_file.write(get_time() + (' # ' if channel == 'Logger' else ' > '))
                                    console_file.write(sline)
                                    console_file.write('\n')
                                console_file.flush()

                                line = line.replace('\r', '')
                                buffer.set_document(Document(buffer.text + line, None), True)
                            await asyncio.sleep(rtt_read_delay)

        console_file.write(f'{ "*" * 80 }\n')

        loop = get_event_loop()
        loop.create_task(task_rtt_read())

        def accept(buff):
            line = f'{buff.text}\n'.replace('\r', '')
            # self.shell_buffer.insert_text(line)
            console_file.write(f'{get_time()} < {line}')
            text = self.shell_buffer.text + line
            self.shell_buffer.set_document(Document(text, None), True)

            prog.rtt_write('Terminal', f'{buff.text}\n')
            return None

        self.input_field.accept_handler = accept

        self.app.run()

        prog.rtt_stop()

    def exit(self, exception=None):
        self.exception = exception
        self.app.exit()
