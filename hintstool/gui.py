import argparse
import re
from abc import ABC, abstractmethod
from enum import Enum

import PySimpleGUI as sg
import yaml
from pathlib2 import Path

"""
    Simple tool to simplify the creation of hints for the learning platform.
    The tool preserves the existing IDs and adds a given prefix to new entries.
    These prefixes can be removed later by another script to separate different
    groups of topic.
    Uses the YAML file format_entry for input and output.
    Since the tool was developed with time constraints, not all functions and
    edge cases were tested.
"""

"""
DEFAULT_PREFIX defines the prefix used for IDs
DEFAULT_LENGTH defines the length of the numeric ID after DEFAULT_PREFIX
AUTO_SAVE makes the tool save after each change to the hints,
which is recommended
"""
DEFAULT_PATH = ""
DEFAULT_PREFIX = "prefix"
DEFAULT_LENGTH = 4
AUTO_SAVE = False


class EntryType(Enum):
    QUESTION = "question",
    ANSWER = "answer"

    @staticmethod
    def from_str(type):
        if type == "question":
            return EntryType.QUESTION
        elif type == "answer":
            return EntryType.ANSWER
        else:
            raise ValueError(type)


class State:
    """
    Handles the state for the tool. This includes the management of hints,
    their creation, removal and editing,
    selecting the following entries and IO operations.
    """

    def __init__(self, path=None, auto_save=AUTO_SAVE):
        self.entries = {EntryType.QUESTION: QuestionsManager(),
                        EntryType.ANSWER: AnswersManager()}
        self.entry_mapping = dict()
        self.selected_entry = None
        self.path = Path(path) if path is not None and path != "" else Path(
            "backup.yml")
        self.auto_save = auto_save

    def reset(self):
        self.__init__()

    def load_from_file(self, path=None):
        """
        Load the hints from the file with the given path into the state data.

        :param path: Path to the file to load
        """
        if path is not None:
            self.path = Path(path)
        content = {}
        with self.path.open(encoding="utf-8") as stream:
            file_content = yaml.safe_load(stream)
        if file_content is None or file_content == [None]:
            return
        for entry in file_content:
            for key in entry:
                content[key] = entry[key]

        for key in content:
            if "question_id" in content[key]:
                question = YAMLParser.create_question_from_yaml(item_id=key,
                                                                **content[key])
                self.entries[EntryType.QUESTION].add_entry(question)
            elif "answer_id" in content[key]:
                answer = YAMLParser.create_answer_from_yaml(item_id=key,
                                                            **content[key])
                self.entries[EntryType.ANSWER].add_entry(answer)
            else:
                print("Found incorrectly formatted entry.")

        self.selected_entry = None

    def save_to_file(self, path=None):
        """
        Saves the hints to the file with the given path.
        If no path is given, then they are saved to the opened file.
        If no file is opened or the contents have not been saved yet,
        the hints are saved to "backup.yml" in the working directory.

        :param path: Path to the file to save to
        """
        if path is not None and path != "":
            self.path = Path(path)
        serialize_format = self._serialize_format()
        serialize_format.sort(key=lambda x: x[0])

        yml_dict = [{entry[0]: format_entry(entry[1])} for entry in
                    serialize_format]

        yaml.add_representer(str, str_representer)
        yaml.add_representer(list, list_representer)
        yaml.add_representer(FormattedList, formatted_list_representer)

        try:
            with self.path.open("w", encoding="utf-8") as file:
                yaml.dump(yml_dict, file, encoding="utf-8", allow_unicode=True,
                          sort_keys=False)
        except FileNotFoundError:
            with Path("crashBackup.yml").open("w", encoding="utf-8") as file:
                yaml.dump(yml_dict, file, encoding="utf-8", allow_unicode=True,
                          sort_keys=False)

    def set_entry(self, idx, entry_type):
        """
        Sets the currently selected entry of the state.

        param entry: Selected entry
        """
        self.selected_entry = self.entries[entry_type].get_object_by_index(idx)

    def selected_entry_type(self):
        return self.selected_entry.get_entry_type()

    def get_content(self, entry_type=EntryType.QUESTION):
        """
        Returns the objects for the selected type of hints.

        :param entry_type: Type of entry to return
        :return: List of hints for type
        """
        return self.entries[entry_type].get_data()

    def swap_next(self, index_1, index_2):
        """
        Swaps the order of the following entries of the selected entry
        """
        if self.selected_entry_type() == EntryType.ANSWER:
            self.selected_entry.swap_next(index_1, index_2)

    def update_next(self, indices):
        """
        Updates the following hints with the given order.
        Fully replaces with indices.
        :param indices: List of indices for next entries
        """
        other_entry_type = self.get_unselected_entry_type()
        next_entries = filter(lambda x: x[0] != -1, self.get_next())
        next_entries_indices = set(map(lambda x: x[0], next_entries))
        next_entry_index = next_entries_indices.symmetric_difference(indices)
        if len(next_entry_index) == 0:
            return
        index = list(next_entry_index)[0]
        entry = self.entries[other_entry_type].get_object_by_index(index)
        entry_id = entry.entry_id
        if index in next_entries_indices:
            self.selected_entry.remove_next_entry(entry_id)
        else:
            if self.selected_entry_type() == EntryType.QUESTION:
                self.selected_entry.pop_next_entry(0)
            self.add_next_entry(entry_id)

    def get_next(self):
        """
        Get the next entries for the selected entry
        :return: Next entries
        """
        other_hint_type = self.get_unselected_entry_type()
        other_hints_manager = self.entries[other_hint_type]
        return other_hints_manager.next_hints(self.selected_entry.next_entries)

    def add_next_entry(self, text):
        """
        Adds a following entry to the selected one.
        Allows for cross-file IDs when given a manual ID.
        :param text: Next entry ID
        """
        self.selected_entry.add_next_entry(text)

    def remove_next_entry(self, index):
        """
        Remove entry at the index from the following hints
        :param index: Index of entry to remove
        """
        self.selected_entry.pop_next_entry(index[0])

    def create_entry(self, prefix, prefix_length,
                     entry_type=EntryType.QUESTION):
        """
        Creates a hint with a given prefix, prefix length and hint type.
        :param prefix: Prefix for the ID
        :param prefix_length: Length of the numeric part of the ID
        :param entry_type: Hint type to create
        :return: The newly created entry
        """
        item_ids = [entry.item_id for entry in
                    self.entries[EntryType.QUESTION].get_data()] + \
                   [entry.item_id for entry in
                    self.entries[EntryType.ANSWER].get_data()]
        collection_ids = self.entries[EntryType.QUESTION].order + self.entries[
            EntryType.ANSWER].order

        item_id = self._get_next_id(item_ids, ("item" + prefix), prefix_length)
        collection_id = self._get_next_id(collection_ids, prefix, prefix_length)

        entry = self.entries[entry_type].create_new_entry(item_id,
                                                          collection_id)

        return entry

    def remove_entry(self, idx=-1):
        """
        Removes entry from the hints list.
        If not given an index, the selected entry is removed.
        :param idx: Either -1 or an index within
        the length of the type of selected entry list
        """
        if idx == -1:
            idx = self.entries[self.selected_entry_type()].order.index(
                self.selected_entry.entry_id)
        other_entry_type = self.get_unselected_entry_type()
        self.entries[self.selected_entry_type()].remove_entry(idx, self.entries[
            other_entry_type])
        self.selected_entry = None

    def get_unselected_entry_type(self):
        entry_type = EntryType.QUESTION if self.selected_entry_type() == EntryType.ANSWER else EntryType.ANSWER
        return entry_type

    def _get_next_id(self, ids, prefix, prefix_length):
        """
        Finds the smallest ID that is unique in a given id list.
        Fills the numeric ID with preceding 0s
        until the given prefix length is reached.
        :param ids: List of existing ids
        :param prefix: Prefix for id
        :param prefix_length: Length of numeric id
        :return: The next unique ID
        """
        ids = [pref_id for pref_id in ids if prefix in pref_id]
        ids.sort(reverse=True)
        highest_id = 0
        if len(ids) > 0:
            prefix_matches = re.search(r"(\d+)", ids[0])
            highest_id = prefix_matches[0] if len(
                prefix_matches.regs) > 0 else 0
        next_id = "{}{}".format(prefix,
                                str(int(highest_id) + 1).zfill(prefix_length))
        return next_id

    def _serialize_format(self):
        """
        Maps the hints to the correct YAML format_entry.
        :return: Formatted entries
        """
        serial_entries = []
        serial_entries += self.entries[EntryType.QUESTION].serialize()
        serial_entries += self.entries[EntryType.ANSWER].serialize()

        return serial_entries


class HintsManager(ABC):
    def __init__(self, order=None, entry_mapping=None):
        self.order = [] if order is None else order
        self.entry_mapping = dict() if entry_mapping is None else entry_mapping

    def add_entry(self, entry):
        entry_id = entry.entry_id
        self.order.append(entry_id)
        self.entry_mapping[entry_id] = entry

    def create_new_entry(self, item_id, entry_id):
        entry = self._create_new_entry(item_id, entry_id)
        self.add_entry(entry)
        return entry

    def remove_entry(self, entry_pos, other_hints_manager):
        entry_id = self.order[entry_pos]
        for entry in other_hints_manager.entry_mapping.values():
            if entry_id in entry.next_entries:
                entry.next_entries.remove(entry_id)
        self.order.pop(entry_pos)
        self.entry_mapping.pop(entry_id)

    def get_data(self):
        return [self.entry_mapping[id] for id in self.order]

    def get_object_by_index(self, idx):
        entry_id = self.order[idx]
        entry = self.entry_mapping[entry_id]
        return entry

    def next_hints(self, id_list):
        next = []
        for id in id_list:
            if id in self.entry_mapping:
                next.append((self.order.index(id), self.entry_mapping[id]))
            else:
                next.append((-1, id))
        return next

    def serialize(self):
        serial_entries = []
        for entry in self.get_data():
            serial_entries.append(entry.serialize())
        return serial_entries

    @abstractmethod
    def _create_new_entry(self, item_id, entry_id):
        pass


class QuestionsManager(HintsManager):
    def _create_new_entry(self, item_id, entry_id):
        return Question(item_id, entry_id)


class AnswersManager(HintsManager):
    def _create_new_entry(self, item_id, entry_id):
        return Answer(item_id, entry_id)


class Entry(ABC):
    def __init__(self, item_id, entry_id, next_entries=None, content=""):
        self.item_id = item_id
        self.entry_id = entry_id
        self.next_entries = [] if next_entries is None else next_entries
        self.content = content

    @abstractmethod
    def get_entry_type(self):
        pass

    @abstractmethod
    def add_next_entry(self, next_entry):
        pass

    @abstractmethod
    def serialize(self):
        pass

    def pop_next_entry(self, idx):
        if idx < len(self.next_entries):
            return self.next_entries.pop(idx)
        return False

    def remove_next_entry(self, next_entry):
        self.next_entries.remove(next_entry)

    def update_content(self, content):
        self.content = content

    def __str__(self):
        return self.content


class YAMLParser:
    @staticmethod
    def create_question_from_yaml(item_id, question_id, following_answer_id,
                                  content):
        content = content.removesuffix("\n")
        next_entries = [following_answer_id] if len(
            following_answer_id) > 0 else []
        return Question(item_id, entry_id=question_id,
                        next_entries=next_entries, content=content)

    @staticmethod
    def create_answer_from_yaml(item_id, answer_id, question_options, content):
        content = content.removesuffix("\n")
        return Answer(item_id, entry_id=answer_id,
                      next_entries=question_options, content=content)


class Question(Entry):
    def get_entry_type(self):
        return EntryType.QUESTION

    def add_next_entry(self, next_entry):
        self.next_entries = [next_entry]

    def serialize(self):
        return (self.item_id, {
            "question_id": self.entry_id,
            "following_answer_id": self.next_entries[0] if len(
                self.next_entries) == 1 else "",
            "content": self.content
        })


class Answer(Entry):
    def get_entry_type(self):
        return EntryType.ANSWER

    def add_next_entry(self, next_entry):
        self.next_entries.append(next_entry)

    def swap_next(self, index_1, index_2):
        next_list = self.next_entries
        if 0 <= index_2 < len(next_list):
            next_list[index_1], next_list[index_2] = next_list[index_2], \
                                                     next_list[index_1]
            self.next_entries = next_list

    def serialize(self):
        return (self.item_id, {
            "answer_id": self.entry_id,
            "question_options": self.next_entries,
            "content": self.content
        })


# Required to parse into appropriate YAML format
class FormattedList(list):
    def __init__(self, ids):
        super().extend(ids)


def format_entry(entry):
    if "question_options" in entry:
        entry["question_options"] = FormattedList(entry["question_options"])
    entry["content"] = entry["content"].replace("\r\n|\r|\n", "\r\n")
    return entry


def str_representer(dumper, data):
    if "\n" in data or "\r" in data:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


def list_representer(dumper, data):
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data,
                                     flow_style=False)


def formatted_list_representer(dumper, data):
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data,
                                     flow_style=True)


# Window and event logic

def make_window(prefix=DEFAULT_PREFIX, prefix_len=DEFAULT_LENGTH):
    """
        Defines and returns the view model for the tool.

        :return: Created window
        :rtype: PySimpleGUI.PySimpleGUI.Window
    """

    sg.theme("Topanga")

    # Overview and list of the questions on the upper left part,
    # including buttons to add and remove them
    questions_frame = sg.Frame(layout=[
        [sg.Button(button_text="Add", size=(8, 1), key="add_question"),
         sg.Button(button_text="Remove", size=(8, 1),
                   key="remove_entry_question")],
        [sg.Listbox(values=[], select_mode=sg.LISTBOX_SELECT_MODE_SINGLE,
                    size=(50, 20), bind_return_key=True,
                    key='question_list', expand_x=True, expand_y=True,
                    horizontal_scroll=True, enable_events=True)]
    ], title="Questions", expand_x=True, expand_y=True)

    # Overview and list of the questions on the lower left part,
    # including buttons to add and remove them
    answers_frame = sg.Frame(layout=[
        [sg.Button(button_text="Add", size=(8, 1), key="add_answer"),
         sg.Button(button_text="Remove", size=(8, 1),
                   key="remove_entry_answer")],
        [sg.Listbox(values=[], select_mode=sg.LISTBOX_SELECT_MODE_SINGLE,
                    size=(50, 20), bind_return_key=True,
                    key='answer_list', expand_x=True, expand_y=True,
                    horizontal_scroll=True, enable_events=True)]
    ], title="Answers", expand_x=True, expand_y=True)

    # Left half of the window
    left_col = [
        [questions_frame],
        [answers_frame],
    ]

    # Inputs for individual prefixes and prefix lengths
    pref_row = sg.Frame(layout=
                        [[sg.Text("Prefix:"),
                          sg.InputText(prefix, key="prefix"),
                          sg.Text("Prefix num. length:"),
                          sg.InputText(str(prefix_len), key="prefix_length")]],
                        title="editor")

    # Editor for the hints
    textbox = sg.Multiline(size=(30, 15), key="textbox", expand_x=True,
                           expand_y=True, enable_events=True,
                           default_text="", disabled=True)

    # Part of the window responsible for editing
    # the following entries for the seleted entry
    next_frame = sg.Frame(layout=[
        [sg.Listbox(values=[], select_mode=sg.LISTBOX_SELECT_MODE_SINGLE,
                    size=(20, 20), bind_return_key=True,
                    key='follow_order',
                    expand_x=True, expand_y=True, horizontal_scroll=True)],
        [sg.Button(button_text="Up", size=(8, 1), key="item_up"),
         sg.Button(button_text="Down", size=(8, 1), key="item_down"),
         sg.Button(button_text="Remove", size=(8, 1), key="item_remove"),
         sg.InputText("prefexample001", size=(20, 1), key="other_id"),
         sg.Button(button_text="Add", size=(8, 1), key="item_add")
         ],
        [sg.Listbox(values=[], select_mode=sg.LISTBOX_SELECT_MODE_SINGLE,
                    size=(30, 20), bind_return_key=True,
                    key='follow',
                    expand_x=True, expand_y=True, horizontal_scroll=True,
                    enable_events=True)]
    ], title="Next entries", expand_x=True, expand_y=True)

    # Right half of the window
    right_col = [
        [pref_row],
        [textbox],
        [next_frame]
    ]

    # Overall layout of the window, including the menu options for the tool
    layout = [[sg.Menu(
        [["File", ["New", "Open    Crtl+o", "Save    Ctrl+s", "Save As"]]])],
        [sg.Text('Hints editor', font='Any 20')],
        [sg.Column(left_col, element_justification='l', expand_x=True,
                   expand_y=True),
         sg.Column(right_col, element_justification='c', expand_x=True,
                   expand_y=True)],
    ]

    window = sg.Window('Hints editor', layout, finalize=True, resizable=True,
                       use_default_focus=False)
    window.set_min_size(window.size)

    # Specifically bind control keys
    window.bind("<Control-s>", "Save")
    window.bind("<Control-o>", "Open")

    # Allow undo for the hints text editor
    textbox.Widget.configure(undo=True)

    return window


def update_window(state, window, components):
    """
        Handles the update of the window after the hints data has been modified.

        :param state: State with the hints data
        :param window: The window to update
        :param components: List of components to update
    """
    if "answer_list" in components:
        indices = []
        if state.selected_entry is not None and state.selected_entry_type() == EntryType.ANSWER:
            indices = window["answer_list"].get_indexes()
        scroll_to_index = max(0, indices[0]) - 10 if len(indices) > 0 else 0
        window["answer_list"].update(
            state.get_content(entry_type=EntryType.ANSWER),
            set_to_index=indices, scroll_to_index=scroll_to_index)

    if "question_list" in components:
        indices = []
        if state.selected_entry is not None and state.selected_entry_type() == EntryType.QUESTION:
            indices = window["question_list"].get_indexes()
        scroll_to_index = max(0, indices[0] - 10) if len(indices) > 0 else 0
        window["question_list"].update(
            state.get_content(entry_type=EntryType.QUESTION),
            set_to_index=indices, scroll_to_index=scroll_to_index)

    if "textbox" in components:
        # Only show text in the hints text editor
        # when an entry is actually selected
        if state.selected_entry is not None:
            window["textbox"].update(state.selected_entry.content,
                                     disabled=False)
        else:
            window["textbox"].update("", disabled=True)

    if "follow" in components:
        if state.selected_entry is not None:
            other_hint_type = state.get_unselected_entry_type()
            if other_hint_type == EntryType.QUESTION:
                select_mode = sg.LISTBOX_SELECT_MODE_MULTIPLE
            else:
                select_mode = sg.LISTBOX_SELECT_MODE_SINGLE
            selected = filter(lambda entry: entry[0] != -1, state.get_next())
            selected = list(map(lambda x: x[0], selected))
            window["item_up"].update(
                disabled=state.selected_entry_type() == EntryType.QUESTION)
            window["item_down"].update(
                disabled=state.selected_entry_type() == EntryType.QUESTION)
            window["follow"].update(
                state.get_content(entry_type=other_hint_type),
                select_mode=select_mode, set_to_index=selected)
        else:
            window["follow"].update([])
    if "follow_order" in components:
        if state.selected_entry is not None:
            next_items = state.get_next()
            next_items = map(lambda x: x[1], next_items)
            window["follow_order"].update(next_items,
                                          select_mode=sg.LISTBOX_SELECT_MODE_SINGLE)
        else:
            window["follow_order"].update([])


def event_helper(event, reverse=False):
    if "question" in event:
        trigger_type = "answer" if reverse else "question"
    elif "answer" in event:
        trigger_type = "question" if reverse else "answer"
    else:
        trigger_type = ""

    return trigger_type


def event_loop(state, window):
    """
    Processes events in the tool window.
    :param state: State object with hints to change
    :param window: Window to listen to
    """
    while True:
        if state.auto_save:
            state.save_to_file()
        event, values = window.read()
        if event is None:
            break
        event_type = event_helper(event, False)

        menu_events(event, state, window)

        if event_type != "":
            if "_list" in event:
                index = window[event].get_indexes()
                if len(index) == 0:
                    continue
                state.set_entry(index[0], EntryType.from_str(event_type))
                update_window(state, window,
                              ["question_list", "answer_list", "textbox",
                               "follow", "follow_order"])

            elif "add_" in event:
                selected_list = event_type + "_list"
                entry = state.create_entry(window["prefix"].get(),
                                           int(window["prefix_length"].get()),
                                           entry_type=EntryType.from_str(
                                               event_type))
                state.selected_entry = entry
                update_window(state, window,
                              [selected_list, "textbox", "follow",
                               "follow_order"])

        if state.selected_entry is not None:
            selected_entry_events(event, state, window)

        window.finalize()


def menu_events(event, state, window):
    """
    Handles all events related to menu options
    """
    if event == sg.WIN_CLOSED or event == 'Exit':
        return
    elif "Open" in event:
        path = sg.popup_get_file("Hints file", no_window=True)
        if path == "" or path == ():
            return
        state.load_from_file(path)
        update_window(state, window,
                      ["answer_list", "question_list", "textbox", "follow",
                       "follow_order"])
    elif "Save" in event:
        if state.path == "" or event == "Save As":
            path = sg.popup_get_file("Hints file", no_window=True, save_as=True)
            if path == "" or path == ():
                return
            state.save_to_file(path=path)
        else:
            state.save_to_file()
    elif "New" == event:
        if state.auto_save:
            state.save_to_file()

        state.reset()
        update_window(state, window,
                      ["answer_list", "question_list", "textbox", "follow",
                       "follow_order"])


def selected_entry_events(event, state, window):
    """
    Handles all events related to the currently selected entry, especially
    editing the content and the manipulation of the following entries.
    """
    event_type = event_helper(event, False)
    if event_type != "" and "remove_entry" in event:
        if EntryType.from_str(
                event.split("_")[2]) != state.selected_entry_type():
            return
        selected_list = event_type + "_list"
        remove_index = window[selected_list].get_indexes()[0]
        state.remove_entry(remove_index)
        update_window(state, window, [selected_list])

    if event == "textbox":
        state.selected_entry.content = window["textbox"].get()
        update_window(state, window, ["question_list", "answer_list"])

    elif event == "follow":
        update_window(state, window, ["follow_order"])
        window.refresh()
        indices = window["follow"].get_indexes()
        state.update_next(indices)
        update_window(state, window, ["follow_order"])

    elif event == "item_up":
        index = window["follow_order"].get_indexes()
        if len(index) != 0:
            state.swap_next(index[0], index[0] - 1)
        update_window(state, window, ["follow_order"])

    elif event == "item_down":
        index = window["follow_order"].get_indexes()
        if len(index) != 0:
            state.swap_next(index[0], index[0] + 1)
        update_window(state, window, ["follow_order"])

    elif event == "item_remove":
        index = window["follow_order"].get_indexes()
        if len(index) != 0:
            state.remove_next_entry(index)
        update_window(state, window, ["follow", "follow_order"])

    elif event == "item_add":
        state.add_next_entry(window["other_id"].get())
        update_window(state, window, ["follow", "follow_order"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parse config values for the tool")

    parser.add_argument("--path", type=str, default="",
                        help="Path to file to open at start")
    parser.add_argument("--prefix", type=str, default=DEFAULT_PREFIX,
                        help="Prefix for the IDs")
    parser.add_argument("--default-len", type=int, default=DEFAULT_LENGTH,
                        help="Length of the numeric part of the ID")
    parser.add_argument("--auto-save", type=bool, default=AUTO_SAVE,
                        help="Automatically save to file when exiting")
    args = parser.parse_args()

    window = make_window(prefix=args.prefix, prefix_len=args.default_len)

    state = State(auto_save=args.auto_save)
    # Only load from file when a valid path is given
    if Path(args.path).is_file():
        state.load_from_file(args.path)
    elif DEFAULT_PATH is not None and Path(DEFAULT_PATH).is_file():
        state.load_from_file(DEFAULT_PATH)

    update_window(state, window,
                  ["answer_list", "question_list", "textbox", "follow",
                   "follow_order"])

    event_loop(state, window)

    window.close()
    if state.auto_save:
        state.save_to_file()
