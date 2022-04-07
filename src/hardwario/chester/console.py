from asyncio.log import logger
import threading
import os
import logging
from functools import partial
from datetime import datetime
from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, VSplit, Window, WindowAlign
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.margins import NumberedMargin, ScrollbarMargin
from prompt_toolkit.widgets import SearchToolbar, TextArea, Frame, HorizontalLine, TextArea
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from .nrfjprog import NRFJProg

logger = logging.getLogger(__name__)


def getTime():
    return datetime.now().strftime('%Y.%m.%d %H:%M:%S.%f')[:23]


class Console:

    def __init__(self, history_file):

        self.logger_buffer = Buffer(read_only=True)
        self.terminal_buffer = Buffer(read_only=True)

        terminal_window = Window(BufferControl(buffer=self.terminal_buffer),
                                 right_margins=[ScrollbarMargin()])
        logger_window = Window(BufferControl(buffer=self.logger_buffer),
                               right_margins=[ScrollbarMargin()])

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
            history=input_history)

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
                                terminal_window,
                                HorizontalLine(),
                                self.input_field,
                                search_field
                            ]
                        ), title="Shell"),
                        Frame(logger_window, title="Log"),
                    ]
                )
            ]
        )

        bindings = KeyBindings()

        @bindings.add("c-c", eager=True)
        @bindings.add("c-q", eager=True)
        def _(event):
            event.app.exit()

        bindings.add("tab")(focus_next)
        bindings.add("s-tab")(focus_previous)

        self.app = Application(
            layout=Layout(root_container, focused_element=self.input_field),
            key_bindings=bindings,
            mouse_support=True,
            full_screen=True,

        )

    def run(self, prog: NRFJProg, console_file):
        prog.rtt_start()

        def task_rtt_read(channel, buffer):
            try:
                while 1:
                    line = prog.rtt_read(channel)
                    if line:
                        # buffer.insert_text(line.replace('\r', ''))
                        for sline in line.splitlines():
                            console_file.write(getTime() + (' # ' if channel == 'Logger' else ' > '))
                            console_file.write(sline)
                            console_file.write('\n')
                        console_file.flush()

                        line = line.replace('\r', '')
                        cpos = buffer.cursor_position + len(line)
                        buffer.set_document(Document(buffer.text + line, cpos), True)
            except Exception:
                return

        console_file.write(f'{ "*" * 80 }\n')

        t1 = threading.Thread(target=task_rtt_read, args=('Logger', self.logger_buffer))
        t2 = threading.Thread(target=task_rtt_read, args=('Terminal', self.terminal_buffer))
        t1.daemon = True
        t2.daemon = True
        t1.start()
        t2.start()

        def accept(buff):
            line = f'{buff.text}\n'.replace('\r', '')
            # self.terminal_buffer.insert_text(line)
            console_file.write(f'{getTime()} < {line}')
            text = self.terminal_buffer.text + line
            cpos = self.terminal_buffer.cursor_position + len(line)
            self.terminal_buffer.set_document(Document(text, cpos), True)

            prog.rtt_write('Terminal', f'{buff.text}\n')
            return None

        self.input_field.accept_handler = accept

        self.app.run()
        prog.rtt_stop()
