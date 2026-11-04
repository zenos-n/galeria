import unittest
from edit_history import History


class HistoryTests(unittest.TestCase):
    def test_pending_change_undo_redo_and_branch(self):
        history=History({'value':0,'strokes':[]});state={'value':20,'strokes':[{'text':'hello'}]}
        self.assertEqual(history.undo(state),{'value':0,'strokes':[]})
        self.assertEqual(history.redo({'value':0,'strokes':[]}),state)
        history.undo(state);history.record({'value':30,'strokes':[]})
        self.assertIsNone(history.redo({'value':30,'strokes':[]}))
        state['strokes'][0]['text']='mutated'
        self.assertEqual(history.past[-1]['value'],30)

    def test_history_is_bounded(self):
        history=History(0)
        for i in range(100):history.record(i)
        self.assertEqual(len(history.past),50)
