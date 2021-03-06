#!/usr/bin/env python
# vim:fileencoding=UTF-8

# This file is part of Yaner.

# Yaner - GTK+ interface for aria2 download mananger
# Copyright (C) 2010-2011  Iven <ivenvd#gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
This module contains the dialog classes of L{yaner}.
"""

import os
import xmlrpc.client

from gi.repository import Gtk, Gio
from gi.repository.Gio import SettingsBindFlags as BindFlags

from yaner.Task import Task
from yaner.ui.Widgets import RightAlignedLabel, AlignedExpander
from yaner.ui.Widgets import MetafileChooserButton, FileChooserEntry, URIsView
from yaner.ui.Widgets import HORIZONTAL, VERTICAL, Box, Grid
from yaner.ui.PoolTree import PoolModel
from yaner.ui.CategoryComboBox import CategoryFilterModel, CategoryComboBox
from yaner.utils.Logging import LoggingMixin

_BT_FILTER_NAME = _('Torrent Files')
_ML_FILTER_NAME = _('Metalink Files')
_BT_MIME_TYPES = {'application/x-bittorrent'}
_ML_MIME_TYPES = {'application/metalink4+xml', 'application/metalink+xml'}
_RESPONSE_RESET = -1
_RESPONSE_SAVE = -2

class _Option(object):
    """An widget wrapper for convert between aria2c needed format and widget
    values.
    """
    def __init__(self, widget, property_, mapper):
        self.widget = widget
        self.property_ = property_
        self.mapper = mapper

    @property
    def value(self):
        """Value for used in XML-RPC."""
        widget_value = self.widget.get_property(self.property_)
        return self.mapper(widget_value)

    @property
    def widget_value(self):
        """Get the value of the widget."""
        return self.widget.get_property(self.property_)

    @widget_value.setter
    def widget_value(self, value):
        """Set the value of the widget."""
        self.widget.set_property(self.property_, value)

    ## Mappers
    default_mapper = lambda x: x
    string_mapper = lambda x: x
    bool_mapper = lambda x: 'true' if x else 'false'
    int_mapper = lambda x: str(int(x))
    float_mapper = lambda x: str(float(x))
    kib_mapper = lambda x: str(int(x) * 1024)
    mib_mapper = lambda x: str(int(x) * 1024 * 1024)
    prioritize_mapper = lambda x: 'head, tail' if x else ''

class _Settings(Gio.Settings):
    """GSettings class for options."""
    def __init__(self, schema_id, delay=False):
        Gio.Settings.__init__(self, schema_id)

        if delay:
            # Don't apply changes to dconf until apply() is called
            self.delay()

        self._delay = delay

    def bind(self, options, flags=BindFlags.DEFAULT):
        keys = self.list_keys()
        for key, option in options.items():
            if key in keys:
                Gio.Settings.bind(self, key, option.widget, option.property_, flags)

    def reset(self, options):
            keys = self.list_keys()
            for key, option in options.items():
                if key in keys:
                    Gio.Settings.reset(self, key)
                    # When in delayed writing mode, widget values doesn't update
                    # when the settings isn't different with the default value,
                    # so update it manually
                    option.widget_value = self.get_value(key).unpack()
            self.apply()

class _TaskNewUI(LoggingMixin):
    """Base class for the UIs of the new task dialog."""

    def __init__(self, task_options, expander_label):
        LoggingMixin.__init__(self)

        self._settings = _Settings('com.kissuki.yaner.task', delay=True)
        self._task_options = task_options.copy()

        expander = AlignedExpander(expander_label)
        self._uris_expander = expander

        vbox = Box(VERTICAL)
        expander.add(vbox)
        self._content_box = vbox

    @property
    def uris_expander(self):
        return self._uris_expander

    @property
    def aria2_options(self):
        return {key: option.value for (key, option) in self._task_options.items()}

    def activate(self, new_options):
        """When the UI changed to this one, bind and update the setting widgets."""
        self._settings.bind(self._task_options)
        for key, option in self._task_options.items():
            try:
                option.widget_value = new_options[key]
            except KeyError:
                pass
        self._uris_expander.show_all()

    def deactivate(self):
        """When the UI changed from this one, unbind the properties."""
        self._settings.revert()

    def response(self, response_id):
        """When dialog responsed, create new task. Returning if the dialog should
        be kept showing.
        """
        if response_id in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            return False
        elif response_id == _RESPONSE_RESET:
            self._settings.reset(self._task_options)
            return True
        elif response_id == _RESPONSE_SAVE:
            self._settings.apply()
            return True
        else:
            return True

class _TaskNewDefaultUI(_TaskNewUI):
    """Default UI of the new task dialog."""
    def __init__(self, task_options, parent):
        _TaskNewUI.__init__(self, task_options,
                            expander_label= _('<b>URIs/Torrent/Metalink File</b>')
                           )

        box = self._content_box

        tooltip = _('Enter URIs here or select Torrent/Metalink files'
                    ' by clicking the icon on the right side.')
        secondary_tooltip = _('Select Torrent/Metalink Files')
        entry = FileChooserEntry(secondary_tooltip,
                                 parent,
                                 Gtk.FileChooserAction.OPEN,
                                 update_entry=False,
                                 mime_list=(
                                     (_BT_FILTER_NAME, _BT_MIME_TYPES),
                                     (_ML_FILTER_NAME, _ML_MIME_TYPES),
                                 ),
                                 truncate_multiline=True,
                                 tooltip_text=tooltip,
                                 secondary_icon_tooltip_text=secondary_tooltip,
                                )
        entry.set_size_request(350, -1)
        box.pack_start(entry)
        self._task_options['uris'] = _Option(entry, 'text', _Option.string_mapper)

        self.uri_entry = entry

    def activate(self, options):
        _TaskNewUI.activate(self, options)
        self.uri_entry.grab_focus()

class _TaskNewNormalUI(_TaskNewUI):
    """Normal UI of the new task dialog."""
    def __init__(self, task_options):
        _TaskNewUI.__init__(self, task_options,
                            expander_label=_('<b>URI(s)</b>')
                           )

        box = self._content_box

        tooltip = _('Specify HTTP(S)/FTP URI:\n'
                    '\thttp://www.example.com/bar.iso\n\n'
                    'Add some mirrors for that file:\n'
                    '\thttps://www.mirror1.com/foo/bar.iso\n'
                    '\tftp://www.mirror2.com/foo/bar.iso\n\n'
                    'Or use Magnet URI(<b>Does not support mirrors</b>):\n'
                    '\tmagnet:?xt=urn:sha1:YNCKHTQCWBTRNJIV4WNAE52SJUQCZO5C\n'
                   )
        uris_view = URIsView(tooltip_markup=tooltip)
        uris_view.set_size_request(350, 70)
        box.pack_start(uris_view)
        self._task_options['uris'] = _Option(uris_view, 'uris',
                                             _Option.default_mapper)

        hbox = Box(HORIZONTAL)
        box.pack_start(hbox)

        # Rename
        tooltip = _('Rename the downloaded file to this name.')

        label = RightAlignedLabel(_('Rename:'), tooltip_text=tooltip)
        hbox.pack_start(label, expand=False)

        entry = Gtk.Entry(tooltip_text=tooltip, activates_default=True)
        hbox.pack_start(entry)
        self._task_options['out'] = _Option(entry, 'text', _Option.string_mapper)

        # Connections
        tooltip = _('The max connections to download the file.')

        label = RightAlignedLabel(_('Connections:'), tooltip_text=tooltip)
        hbox.pack_start(label, expand=False)

        adjustment = Gtk.Adjustment(lower=1, upper=1024, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True,
                                     tooltip_text=tooltip)
        hbox.pack_start(spin_button)
        self._task_options['split'] = _Option(spin_button, 'value',
                                              _Option.int_mapper)

        self._uris_view = uris_view

    @property
    def uris_view(self):
        return self._uris_view

    def activate(self, options):
        _TaskNewUI.activate(self, options)
        self._uris_view.grab_focus()

    def response(self, response_id):
        if response_id == Gtk.ResponseType.OK:
            options = self.aria2_options

            # Workaround for aria2 bug#3527521
            options.pop('bt-prioritize-piece')

            category = options.pop('category')
            uris = options.pop('uris')
            if not uris:
                return True

            name = options['out'] if options['out'] else os.path.basename(uris[0])

            Task(name=name, uris=uris, options=options, category=category).start()

            return False
        else:
            return _TaskNewUI.response(self, response_id)

class _TaskNewBTUI(_TaskNewUI):
    """BT UI of the new task dialog."""
    def __init__(self, task_options):
        _TaskNewUI.__init__(self, task_options,
                            expander_label=_('<b>Torrent File</b>')
                           )

        box = self._content_box

        button = MetafileChooserButton(title=_('Select torrent file'),
                                       mime_types=_BT_MIME_TYPES,
                                      )
        button.set_size_request(350, -1)
        box.pack_start(button)
        self._task_options['torrent_filename'] = _Option(button, 'filename',
                                                         _Option.string_mapper)

    def response(self, response_id):
        if response_id == Gtk.ResponseType.OK:
            options = self.aria2_options

            torrent_filename = options.pop('torrent_filename')
            if torrent_filename is None:
                return True
            else:
                name = os.path.basename(torrent_filename)
                with open(torrent_filename, 'br') as torrent_file:
                    torrent = xmlrpc.client.Binary(torrent_file.read())

            uris = options.pop('uris')
            category = options.pop('category')

            Task(name=name, torrent=torrent, uris=uris,
                 options=options, category=category).start()

            return False
        else:
            return _TaskNewUI.response(self, response_id)

class _TaskNewMLUI(_TaskNewUI):
    """Metalink UI of the new task dialog."""
    def __init__(self, task_options):
        _TaskNewUI.__init__(self, task_options,
                            expander_label=_('<b>Metalink File</b>')
                           )

        box = self._content_box

        button = MetafileChooserButton(title=_('Select metalink file'),
                                       mime_types=_ML_MIME_TYPES,
                                      )
        button.set_size_request(350, -1)
        box.pack_start(button)
        self._task_options['metalink_filename'] = _Option(button, 'filename',
                                                          _Option.string_mapper)

    def response(self, response_id):
        if response_id == Gtk.ResponseType.OK:
            options = self.aria2_options

            # Workaround for aria2 bug#3527521
            options.pop('uris')

            metalink_filename = options.pop('metalink_filename')
            if metalink_filename is None:
                return True
            else:
                name = os.path.basename(metalink_filename)
                with open(metalink_filename, 'br') as metalink_file:
                    metafile = xmlrpc.client.Binary(metalink_file.read())

            category = options.pop('category')

            Task(name=name, metafile=metafile, options=options,
                 category=category).start()
            return False
        else:
            return _TaskNewUI.response(self, response_id)

class TaskNewDialog(Gtk.Dialog, LoggingMixin):
    """Dialog for creating new tasks."""
    def __init__(self, pool_model, *args, **kwargs):
        Gtk.Dialog.__init__(self, title=_('Create New Task'), *args, **kwargs)
        LoggingMixin.__init__(self)

        self._ui = None
        self._default_ui = None
        self._normal_ui = None
        self._bt_ui = None
        self._ml_ui = None

        self._task_options = {}

        ### Action Area
        action_area = self.get_action_area()
        action_area.set_layout(Gtk.ButtonBoxStyle.START)

        button = Gtk.Button.new_from_stock(Gtk.STOCK_CANCEL)
        self.add_action_widget(button, Gtk.ResponseType.CANCEL)
        action_area.set_child_secondary(button, True)

        image = Gtk.Image.new_from_stock(Gtk.STOCK_GO_DOWN, Gtk.IconSize.BUTTON)
        button = Gtk.Button(_('_Download'), image=image, use_underline=True)
        self.add_action_widget(button, Gtk.ResponseType.OK)
        action_area.set_child_secondary(button, True)

        advanced_buttons = []

        image = Gtk.Image.new_from_stock(Gtk.STOCK_UNDO, Gtk.IconSize.BUTTON)
        button = Gtk.Button(_('_Reset Settings'), image=image, use_underline=True)
        button.set_no_show_all(True)
        self.add_action_widget(button, _RESPONSE_RESET)
        advanced_buttons.append(button)

        image = Gtk.Image.new_from_stock(Gtk.STOCK_SAVE, Gtk.IconSize.BUTTON)
        button = Gtk.Button(_('_Save Settings'), image=image, use_underline=True)
        button.set_no_show_all(True)
        self.add_action_widget(button, _RESPONSE_SAVE)
        advanced_buttons.append(button)

        ### Content Area
        content_area = self.get_content_area()

        vbox = Box(VERTICAL)
        content_area.add(vbox)
        self._main_vbox = vbox

        ## Save to
        expander = AlignedExpander(_('<b>Save to...</b>'))
        expander.connect_after('activate', self.update_size)
        vbox.pack_start(expander)
        self.save_expander = expander

        hbox = Box(HORIZONTAL)
        expander.add(hbox)

        # Directory
        tooltip = _('Select the directory to save files')
        entry = FileChooserEntry(_('Select download directory'),
                                 self,
                                 Gtk.FileChooserAction.SELECT_FOLDER,
                                 tooltip_text=tooltip
                                )
        hbox.pack_end(entry)
        self._task_options['dir'] = _Option(entry, 'text', _Option.string_mapper)

        model = CategoryFilterModel(pool_model)
        combo_box = CategoryComboBox(model, self)
        combo_box.connect('changed', self._on_category_cb_changed, entry)
        combo_box.set_active(0)
        hbox.pack_start(combo_box)
        self._task_options['category'] = _Option(combo_box, 'category',
                                                 _Option.default_mapper)

        ## Advanced
        expander = AlignedExpander(_('<b>Advanced</b>'), expanded=False)
        expander.connect_after('activate',
                               self._on_advanced_expander_activated,
                               advanced_buttons)
        expander.connect_after('activate', self.update_size)
        vbox.pack_end(expander)
        self.advanced_expander = expander

        notebook = Gtk.Notebook()
        expander.add(notebook)

        ## Normal Task Page
        label = Gtk.Label(_('Normal Task'))
        vbox = Box(VERTICAL, border_width=5)
        notebook.append_page(vbox, label)

        grid = Grid()
        vbox.pack_start(grid, expand=False)

        # Speed Limit
        tooltip = _('Upload speed limit, in KiB/s.')

        label = RightAlignedLabel(_('Upload Limit:'), tooltip_text=tooltip)
        grid.attach(label, 0, 0)

        adjustment = Gtk.Adjustment(lower=0, upper=4096, step_increment=10)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True,
                                     tooltip_text=tooltip)
        grid.attach(spin_button, 1, 0)
        self._task_options['max-upload-limit'] = _Option(spin_button, 'value',
                                                         _Option.kib_mapper)

        tooltip = _('Download speed limit, in KiB/s.')

        label = RightAlignedLabel(_('Download Limit:'), tooltip_text=tooltip)
        grid.attach(label, 2, 0)

        adjustment = Gtk.Adjustment(lower=0, upper=4096, step_increment=10)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True,
                                     tooltip_text=tooltip)
        grid.attach(spin_button, 3, 0)
        self._task_options['max-download-limit'] = _Option(spin_button, 'value',
                                                           _Option.kib_mapper)

        # Retry
        tooltip = _('Number of retries.')

        label = RightAlignedLabel(_('Max Retries:'), tooltip_text=tooltip)
        grid.attach(label, 0, 1)

        adjustment = Gtk.Adjustment(lower=0, upper=60, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True,
                                     tooltip_text=tooltip)
        grid.attach(spin_button, 1, 1)
        self._task_options['max-tries'] = _Option(spin_button, 'value',
                                                  _Option.int_mapper)

        tooltip = _('Time to wait before retries, in seconds.')

        label = RightAlignedLabel(_('Retry Interval:'), tooltip_text=tooltip)
        grid.attach(label, 2, 1)

        adjustment = Gtk.Adjustment(lower=0, upper=60, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True,
                                     tooltip_text=tooltip)
        grid.attach(spin_button, 3, 1)
        self._task_options['retry-wait'] = _Option(spin_button, 'value',
                                                   _Option.int_mapper)

        # Timeout
        tooltip = _('Download timeout, in seconds.')

        label = RightAlignedLabel(_('Timeout:'), tooltip_text=tooltip)
        grid.attach(label, 0, 2)

        adjustment = Gtk.Adjustment(lower=1, upper=300, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True,
                                     tooltip_text=tooltip)
        grid.attach(spin_button, 1, 2)
        self._task_options['timeout'] = _Option(spin_button, 'value',
                                                _Option.int_mapper)

        tooltip = _('Timeout to connect HTTP/FTP/proxy server, in seconds.')

        label = RightAlignedLabel(_('Connect Timeout:'), tooltip_text=tooltip)
        grid.attach(label, 2, 2)

        adjustment = Gtk.Adjustment(lower=1, upper=300, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True,
                                     tooltip_text=tooltip)
        grid.attach(spin_button, 3, 2)
        self._task_options['connect-timeout'] = _Option(spin_button, 'value',
                                                        _Option.int_mapper)

        # Split and Connections
        tooltip = _('Minimal size to split the file into pieces, in MiB.')

        label = RightAlignedLabel(_('Split Size:'), tooltip_text=tooltip)
        grid.attach(label, 0, 3)

        adjustment = Gtk.Adjustment(lower=1, upper=1024, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True,
                                     tooltip_text=tooltip)
        grid.attach(spin_button, 1, 3)
        self._task_options['min-split-size'] = _Option(spin_button, 'value',
                                                       _Option.mib_mapper)

        tooltip = _('Max connections per server.')
        label = RightAlignedLabel(_('Per Server Connections:'), tooltip_text=tooltip)
        grid.attach(label, 2, 3)

        adjustment = Gtk.Adjustment(lower=1, upper=10, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True,
                                     tooltip_text=tooltip)
        grid.attach(spin_button, 3, 3)
        self._task_options['max-connection-per-server'] = _Option(
            spin_button, 'value', _Option.int_mapper)

        # Referer
        tooltip = _('The referrer page of the download.')
        label = RightAlignedLabel(_('Referer:'), tooltip_text=tooltip)
        grid.attach(label, 0, 4)

        entry = Gtk.Entry(activates_default=True, tooltip_text=tooltip)
        grid.attach(entry, 1, 4, 3, 1)
        self._task_options['referer'] = _Option(entry, 'text',
                                                _Option.string_mapper)

        # Header
        label = RightAlignedLabel(_('HTTP Header:'))
        grid.attach(label, 0, 5)

        entry = Gtk.Entry(activates_default=True)
        grid.attach(entry, 1, 5, 3, 1)
        self._task_options['header'] = _Option(entry, 'text',
                                               _Option.string_mapper)

        ## BT Task Page
        label = Gtk.Label(_('BitTorrent'))
        vbox = Box(VERTICAL, border_width=5)
        notebook.append_page(vbox, label)

        grid = Grid()
        vbox.pack_start(grid, expand=False)

        # Limit
        label = RightAlignedLabel(_('Max open files:'))
        grid.attach(label, 0, 0)

        adjustment = Gtk.Adjustment(lower=1, upper=1024, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True)
        grid.attach(spin_button, 1, 0)
        self._task_options['bt-max-open-files'] = _Option(spin_button, 'value',
                                                          _Option.int_mapper)

        label = RightAlignedLabel(_('Max peers:'))
        grid.attach(label, 2, 0)

        adjustment = Gtk.Adjustment(lower=1, upper=1024, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True)
        grid.attach(spin_button, 3, 0)
        self._task_options['bt-max-peers'] = _Option(spin_button, 'value',
                                                     _Option.int_mapper)

        # Seed
        tooltip = _('Seed time, in minutes')

        label = RightAlignedLabel(_('Seed time:'), tooltip_text=tooltip)
        grid.attach(label, 0, 1)

        adjustment = Gtk.Adjustment(lower=0, upper=7200, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True,
                                     tooltip_text=tooltip)
        grid.attach(spin_button, 1, 1)
        self._task_options['seed-time'] = _Option(spin_button, 'value',
                                                  _Option.int_mapper)

        label = RightAlignedLabel(_('Seed ratio:'))
        grid.attach(label, 2, 1)

        adjustment = Gtk.Adjustment(lower=0, upper=20, step_increment=.1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True, digits=1)
        grid.attach(spin_button, 3, 1)
        self._task_options['seed-ratio'] = _Option(spin_button, 'value',
                                                   _Option.float_mapper)

        # Timeout
        tooltip = _('Download timeout, in seconds.')

        label = RightAlignedLabel(_('Timeout:'), tooltip_text=tooltip)
        grid.attach(label, 0, 2)

        adjustment = Gtk.Adjustment(lower=1, upper=300, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True,
                                     tooltip_text=tooltip)
        grid.attach(spin_button, 1, 2)
        self._task_options['bt-tracker-timeout'] = _Option(spin_button, 'value',
                                                           _Option.int_mapper)

        tooltip = _('Timeout to establish connection to trackers, in seconds.')

        label = RightAlignedLabel(_('Connect Timeout:'), tooltip_text=tooltip)
        grid.attach(label, 2, 2)

        adjustment = Gtk.Adjustment(lower=1, upper=300, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True,
                                     tooltip_text=tooltip)
        grid.attach(spin_button, 3, 2)
        self._task_options['bt-tracker-connect-timeout'] = _Option(
            spin_button, 'value', _Option.int_mapper)

        tooltip = _('Try to download first and last pieces first.')
        label = RightAlignedLabel(_('Preview Mode:'), tooltip_text=tooltip)
        grid.attach(label, 0, 3)
        switch = Gtk.Switch(tooltip_text=tooltip)
        grid.attach(switch, 1, 3)
        self._task_options['bt-prioritize-piece'] = _Option(
            switch, 'active', _Option.prioritize_mapper)

        tooltip = _('Convert downloaded torrent files to BitTorrent tasks.')
        label = RightAlignedLabel(_('Follow Torrent:'), tooltip_text=tooltip)
        grid.attach(label, 2, 3)
        switch = Gtk.Switch(tooltip_text=tooltip)
        grid.attach(switch, 3, 3)
        self._task_options['follow-torrent'] = _Option(switch, 'active',
                                                       _Option.bool_mapper)

        # Mirrors
        tooltip = _('For single file torrents, a mirror can be a ' \
                    'complete URI pointing to the resource or if the mirror ' \
                    'ends with /, name in torrent file is added. For ' \
                    'multi-file torrents, name and path in torrent are ' \
                    'added to form a URI for each file.')
        expander = AlignedExpander(_('Mirrors'), expanded=False, tooltip_text=tooltip)
        expander.connect_after('activate', self.update_size)
        grid.attach(expander, 0, 4, 4, 1)
        #vbox.pack_start(expander, expand=False)

        uris_view = URIsView()
        uris_view.set_size_request(-1, 70)
        expander.add(uris_view)
        self._task_options['uris'] = _Option(uris_view, 'uris',
                                             _Option.default_mapper)

        ## Metalink Page
        label = Gtk.Label(_('Metalink'))
        vbox = Box(VERTICAL, border_width=5)
        notebook.append_page(vbox, label)

        grid = Grid(halign=Gtk.Align.CENTER)
        vbox.pack_start(grid, expand=False)

        label = RightAlignedLabel(_('Preferred locations:'))
        grid.attach(label, 0, 0)

        entry = Gtk.Entry()
        grid.attach(entry, 1, 0)
        self._task_options['metalink-location'] = _Option(entry, 'text',
                                                          _Option.string_mapper)

        label = RightAlignedLabel(_('Language:'))
        grid.attach(label, 0, 1)

        entry = Gtk.Entry()
        grid.attach(entry, 1, 1)
        self._task_options['metalink-language'] = _Option(entry, 'text',
                                                          _Option.string_mapper)

        label = RightAlignedLabel(_('Version:'))
        grid.attach(label, 0, 2)

        entry = Gtk.Entry()
        grid.attach(entry, 1, 2)
        self._task_options['metalink-version'] = _Option(entry, 'text',
                                                         _Option.string_mapper)

        label = RightAlignedLabel(_('OS:'))
        grid.attach(label, 0, 3)

        entry = Gtk.Entry()
        grid.attach(entry, 1, 3)
        self._task_options['metalink-os'] = _Option(entry, 'text',
                                                    _Option.string_mapper)

        tooltip = _('Convert downloaded metalink files to Metalink tasks.')

        label = RightAlignedLabel(_('Follow Metalink:'), tooltip_text=tooltip)
        grid.attach(label, 0, 4)

        switch = Gtk.Switch(tooltip_text=tooltip)
        grid.attach(switch, 1, 4)
        self._task_options['follow-metalink'] = _Option(switch, 'active',
                                                        _Option.bool_mapper)

        ## Miscellaneous Page
        label = Gtk.Label(_('Miscellaneous'))
        vbox = Box(VERTICAL, border_width=5)
        notebook.append_page(vbox, label)

        grid = Grid()
        vbox.pack_start(grid, expand=False)

        # Overwrite and Rename
        tooltip = _("Restart download from scratch if the corresponding"
                    " control file doesn't exist.")

        label = RightAlignedLabel(_('Allow Overwrite:'), tooltip_text=tooltip)
        grid.attach(label, 0, 0)

        switch = Gtk.Switch(tooltip_text=tooltip)
        grid.attach(switch, 1, 0)
        self._task_options['allow-overwrite'] = _Option(switch, 'active',
                                                        _Option.bool_mapper)

        tooltip = _('Rename file name if the same file already exists.')

        label = RightAlignedLabel(_('Auto Rename Files:'), tooltip_text=tooltip)
        grid.attach(label, 2, 0)

        switch = Gtk.Switch(tooltip_text=tooltip)
        grid.attach(switch, 3, 0)
        self._task_options['auto-file-renaming'] = _Option(switch, 'active',
                                                           _Option.bool_mapper)

        tooltip = _('Format: [http://][USER:PASSWORD@]HOST[:PORT]')
        label = RightAlignedLabel(_('Proxy:'), tooltip_text=tooltip)
        grid.attach(label, 0, 1)

        entry = Gtk.Entry(activates_default=True, tooltip_text=tooltip)
        entry.set_placeholder_text(tooltip)
        grid.attach(entry, 1, 1, 3, 1)
        self._task_options['all-proxy'] = _Option(entry, 'text',
                                                  _Option.string_mapper)

        # Authorization
        expander = AlignedExpander(_('Authorization'), expanded=False)
        expander.connect_after('activate', self.update_size)
        vbox.pack_start(expander, expand=False)

        grid = Grid()
        expander.add(grid)

        label = RightAlignedLabel(_('HTTP User:'))
        grid.attach(label, 0, 0)

        entry = Gtk.Entry(activates_default=True)
        grid.attach(entry, 1, 0)
        self._task_options['http-user'] = _Option(entry, 'text',
                                                  _Option.string_mapper)

        label = RightAlignedLabel(_('Password:'))
        grid.attach(label, 2, 0)

        entry = Gtk.Entry(activates_default=True)
        grid.attach(entry, 3, 0)
        self._task_options['http-passwd'] = _Option(entry, 'text',
                                                    _Option.string_mapper)

        label = RightAlignedLabel(_('FTP User:'))
        grid.attach(label, 0, 1)

        entry = Gtk.Entry(activates_default=True)
        grid.attach(entry, 1, 1)
        self._task_options['ftp-user'] = _Option(entry, 'text',
                                                 _Option.string_mapper)

        label = RightAlignedLabel(_('Password:'))
        grid.attach(label, 2, 1)

        entry = Gtk.Entry(activates_default=True)
        grid.attach(entry, 3, 1)
        self._task_options['ftp-passwd'] = _Option(entry, 'text',
                                                   _Option.string_mapper)

        self.show_all()

    @property
    def default_ui(self):
        """Get the default UI."""
        if self._default_ui is None:
            ui = _TaskNewDefaultUI(self._task_options, self)
            ui.uri_entry.connect('response', self._on_metafile_selected)
            ui.uri_entry.connect('changed', self._on_default_entry_changed)
            self._default_ui = ui
        return self._default_ui

    @property
    def normal_ui(self):
        """Get the normal UI."""
        if self._normal_ui is None:
            ui = _TaskNewNormalUI(self._task_options)
            text_buffer = ui.uris_view.text_buffer
            text_buffer.connect('changed', self._on_normal_uris_view_changed)
            self._normal_ui = ui
        return self._normal_ui

    @property
    def bt_ui(self):
        """Get the BT UI."""
        if self._bt_ui is None:
            self._bt_ui = _TaskNewBTUI(self._task_options)
        return self._bt_ui

    @property
    def ml_ui(self):
        """Get the ML UI."""
        if self._ml_ui is None:
            self._ml_ui = _TaskNewMLUI(self._task_options)
        return self._ml_ui

    def _on_advanced_expander_activated(self, expander, buttons):
        """When advanced button activated, show or hide advanced buttons."""
        for button in buttons:
            if expander.get_expanded():
                button.show()
            else:
                button.hide()

    def _on_category_cb_changed(self, category_cb, entry):
        """When category combo box changed, update the directory entry."""
        iter_ = category_cb.get_active_iter()
        model = category_cb.get_model()
        presentable = model.get_value(iter_, PoolModel.COLUMNS.PRESENTABLE)
        entry.set_text(presentable.directory)
        self.logger.debug('Category is changed to {}.'.format(presentable))

    def _on_metafile_selected(self, dialog, response_id):
        """When meta file chooser dialog responsed, switch to torrent or metalink
        mode."""
        if response_id == Gtk.ResponseType.ACCEPT:
            filename = dialog.get_filename()
            current_filter = dialog.get_filter().get_name()
            if current_filter == _BT_FILTER_NAME:
                self.logger.info(
                    'Torrent file selected, changing to bittorrent UI...')
                self.set_ui(self.bt_ui, {'torrent_filename': filename})
            elif current_filter == _ML_FILTER_NAME:
                self.logger.info(
                    'Metalink file selected, changing to metalink UI...')
                self.set_ui(self.ml_ui, {'metalink_filename': filename})
            else:
                raise RuntimeError('No such filter' + current_filter)

    def _on_default_entry_changed(self, entry):
        """When the entry in the default content box changed, switch to normal
        mode."""
        # When default UI activated, the entry text is cleared, we should
        # ignore this.
        if self._ui is not self.normal_ui:
            self.logger.info('URIs inputed, changing to normal UI...')
            self.set_ui(self.normal_ui, {'uris': entry.get_text()})

    def _on_normal_uris_view_changed(self, text_buffer):
        """When the uris view in the normal UI cleared, switch to default mode."""
        if text_buffer.get_property('text') == '':
            self.logger.info('URIs cleared, changing to default UI...')
            self.set_ui(self.default_ui, {'uris': ''})
        elif self._ui is not self.normal_ui:
            # When it's already the normal UI, and the text of the
            # URIs view is set (from the browser), the textview will
            # firstly been cleared, and it changes to default UI,
            # in this case we need to set the UI back to normal UI.
            self.set_ui(self.normal_ui, {})

    def do_response(self, response_id):
        """Create a new download task if uris are provided."""
        if not self._ui.response(response_id):
            self.hide()

    def set_ui(self, new_ui, options=None):
        """Set the UI of the dialog."""
        # Remove current child of uris_expander
        if self._ui is not new_ui:
            main_vbox = self._main_vbox
            if self._ui is not None:
                main_vbox.remove(self._ui.uris_expander)
            main_vbox.pack_start(new_ui.uris_expander)
            main_vbox.reorder_child(new_ui.uris_expander, 0)

        if new_ui is self.default_ui:
            # Hide the advanced buttons when changing to default UI
            if self.advanced_expander.get_expanded():
                self.advanced_expander.emit('activate')
            self.advanced_expander.hide()
            self.save_expander.hide()
        else:
            self.advanced_expander.show_all()
            self.save_expander.show_all()

        if self._ui is not None:
            self._ui.deactivate()

        new_ui.activate(options)

        self.update_size()

        self._ui = new_ui

    def update_size(self, widget=None):
        """Update the size of the dialog."""
        content_area = self.get_content_area()
        size = content_area.get_preferred_size()[0]
        self.resize(size.width, size.height)

    def run(self, options=None):
        """Popup new task dialog."""
        if options is None:
            self.set_ui(self.default_ui, {'uris': ''})
        elif 'torrent_filename' in options:
            self.set_ui(self.bt_ui, options)
        elif 'metalink_filename' in options:
            self.set_ui(self.ml_ui, options)
        else:
            self.set_ui(self.normal_ui, options)

        self.logger.info('Running new task dialog...')

        Gtk.Dialog.run(self)

class PreferencesDialog(Gtk.Dialog, LoggingMixin):
    """Dialog for global preferences."""
    def __init__(self, *args, **kwargs):
        Gtk.Dialog.__init__(self,
                            title=_('Preferences'),
                            buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE),
                            *args, **kwargs)
        LoggingMixin.__init__(self)

        self.preferences = {}

        ### Content Area
        content_area = self.get_content_area()

        notebook = Gtk.Notebook()
        content_area.add(notebook)

        ## General Page
        label = Gtk.Label(_('General'))
        vbox = Box(VERTICAL, border_width=5)
        notebook.append_page(vbox, label)

        ## Download Page
        label = Gtk.Label(_('Download'))
        vbox = Box(VERTICAL, border_width=5)
        notebook.append_page(vbox, label)

        grid = Grid()
        vbox.pack_start(grid, expand=False)

        label = RightAlignedLabel(_('Max Concurrent Tasks:'))
        grid.attach(label, 0, 0)

        adjustment = Gtk.Adjustment(lower=1, upper=64, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True)
        grid.attach(spin_button, 1, 0)
        self._preferences['max-concurrent-downloads'] = _Option(
            spin_button, 'value', _Option.int_mapper)

        label = RightAlignedLabel(_('Global Upload Limit(KiB/s):'))
        grid.attach(label, 0, 1)

        adjustment = Gtk.Adjustment(lower=0, upper=4096, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True)
        grid.attach(spin_button, 1, 1)
        self._preferences['max-overall-upload-limit'] = _Option(
            spin_button, 'value', _Option.kib_mapper)

        label = RightAlignedLabel(_('Global Download Limit(KiB/s):'))
        grid.attach(label, 0, 2)

        adjustment = Gtk.Adjustment(lower=0, upper=4096, step_increment=1)
        spin_button = Gtk.SpinButton(adjustment=adjustment, numeric=True)
        grid.attach(spin_button, 1, 2)
        self._preferences['max-overall-download-limit'] = _Option(
            spin_button, 'value', _Option.kib_mapper)

        self.show_all()

    def run(self, options=None):
        """Popup new task dialog."""
        self.logger.info('Running preferences dialog...')

        Gtk.Dialog.run(self)
        self.hide()

