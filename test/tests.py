import unittest

from pathlib2 import Path

from hintstool.gui import State, EntryType


class TestEntryType(unittest.TestCase):
    def test_entry_type_from_str_answer(self):
        assert EntryType.from_str("answer") == EntryType.ANSWER

    def test_entry_type_from_str_question(self):
        assert EntryType.from_str("question") == EntryType.QUESTION

    def test_entry_type_from_str_invalid(self):
        with self.assertRaises(ValueError):
            EntryType.from_str("test")


class TestLoadingFile(unittest.TestCase):

    def test_loading_resources(self):
        state = State(path="resources/hints_test.yml")
        state.load_from_file()


class TestLoadingFunctions(unittest.TestCase):

    def setUp(self):
        state = State(path="resources/hints_test.yml")
        state.load_from_file()
        self.state = state

    def test_select_state_question(self):
        self.state.set_entry(0, EntryType.QUESTION)
        assert self.state.selected_entry_type() == EntryType.QUESTION
        assert self.state.selected_entry.content == "Question1"
        assert self.state.selected_entry.next_entries == ["prefix001"]
        assert self.state.selected_entry.item_id == "itemprefix001"
        assert self.state.selected_entry.entry_id == "prefix001"

    def test_select_state_answer(self):
        self.state.set_entry(0, EntryType.ANSWER)
        assert self.state.selected_entry_type() == EntryType.ANSWER
        assert self.state.selected_entry.content == "Answer1"
        assert self.state.selected_entry.next_entries == ["prefix002"]
        assert self.state.selected_entry.item_id == "itemprefix004"
        assert self.state.selected_entry.entry_id == "prefix001"

    def test_get_content(self):
        content = self.state.get_content(EntryType.QUESTION)
        assert len(content) == 4
        ordered_ids = [entry.item_id for entry in content]
        expected_ids = ["itemprefix001", "itemprefix002", "itemprefix003",
                        "itemprefix007"]

    def test_size(self):
        assert_num_entries(self.state, 4, 3)

    def test_save_to_file(self):
        path = "resources/hints_test_copy.yml"
        self.state.save_to_file(path=path)
        self.state.load_from_file(path=path)
        Path(path).unlink()

    def test_reset(self):
        self.state.reset()
        assert_num_entries(self.state, 0, 0)
        assert self.state.selected_entry is None
        assert str(self.state.path) == "backup.yml"


class TestStateManipulation(unittest.TestCase):
    def setUp(self):
        state = State()
        path = "resources/hints_test.yml"
        state.load_from_file(path)
        self.state = state

        assert_num_entries(self.state, 4, 3)

    def test_create_question(self):
        entry = self.state.create_entry("prefix", 3, EntryType.QUESTION)
        assert_num_entries(self.state, 5, 3)
        assert entry.item_id == "itemprefix008"
        assert entry.entry_id == "prefix005"
        assert entry.content == ""
        assert entry.next_entries == []

    def test_create_answer(self):
        entry = self.state.create_entry("prefix", 3, EntryType.ANSWER)
        assert_num_entries(self.state, 4, 4)
        assert entry.item_id == "itemprefix008"
        assert entry.entry_id == "prefix005"
        assert entry.content == ""
        assert entry.next_entries == []


class TestStateManipulationQuestions(TestStateManipulation):

    def setUp(self):
        super(TestStateManipulationQuestions, self).setUp()
        # itemprefix002
        self.state.set_entry(1, EntryType.QUESTION)

    def test_remove_question(self):
        self.state.remove_entry()
        assert_num_entries(self.state, 3, 3)
        assert self.state.selected_entry is None
        assert len(
            get_entry_by_id(self.state, "itemprefix004").next_entries) == 0

    def test_update_next_remove(self):
        assert self.state.selected_entry.next_entries[0] == "prefix002"
        assert len(self.state.selected_entry.next_entries) == 1
        self.state.update_next([0])
        assert self.state.selected_entry.next_entries[0] == "prefix001"
        assert len(self.state.selected_entry.next_entries) == 1

    def test_update_next_add(self):
        assert len(self.state.selected_entry.next_entries) == 1
        self.state.update_next([])
        assert len(self.state.selected_entry.next_entries) == 0


class TestStateManipulationAnswers(TestStateManipulation):

    def setUp(self):
        super(TestStateManipulationAnswers, self).setUp()
        # itemprefix005
        self.state.set_entry(1, EntryType.ANSWER)

    def test_remove_answer(self):
        self.state.remove_entry()
        assert_num_entries(self.state, 4, 2)
        assert self.state.selected_entry is None
        assert len(
            get_entry_by_id(self.state, "itemprefix002").next_entries) == 0

    def test_swap_order(self):
        assert self.state.selected_entry.next_entries[0] == "prefix001"
        assert self.state.selected_entry.next_entries[1] == "prefix003"
        self.state.swap_next(0, 1)
        assert_num_entries(self.state, 4, 3)
        assert self.state.selected_entry.next_entries[0] == "prefix003"
        assert self.state.selected_entry.next_entries[1] == "prefix001"

    def test_update_next_remove(self):
        assert self.state.selected_entry.next_entries[0] == "prefix001"
        assert len(self.state.selected_entry.next_entries) == 3
        self.state.update_next([2, 3])
        assert self.state.selected_entry.next_entries[0] != "prefix001"
        assert len(self.state.selected_entry.next_entries) == 2

    def test_update_next_add(self):
        assert len(self.state.selected_entry.next_entries) == 3
        self.state.update_next([0, 1, 2, 3])
        assert self.state.selected_entry.next_entries[3] == "prefix002"
        assert len(self.state.selected_entry.next_entries) == 4


class TestStateManipulationWithoutSelected(TestStateManipulation):
    def setUp(self):
        super(TestStateManipulationWithoutSelected, self).setUp()

    def test_no_selection(self):
        assert self.state.selected_entry is None


def get_entry_by_id(state, item_id):
    combined = state.get_content(EntryType.QUESTION) + state.get_content(
        EntryType.ANSWER)
    for entry in combined:
        if entry.item_id == item_id:
            return entry


def assert_num_entries(state, num_questions, num_answers):
    assert_len_of_data_structure(state, EntryType.QUESTION, num_questions)
    assert_len_of_data_structure(state, EntryType.ANSWER, num_answers)


def assert_len_of_data_structure(state, entry_type, num):
    assert len(state.entries[entry_type].get_data()) == num
    assert len(state.entries[entry_type].order) == num
    assert len(state.entries[entry_type].entry_mapping) == num


if __name__ == '__main__':
    unittest.main()
