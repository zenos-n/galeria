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

    def test_saved_state_survives_history_eviction_and_detects_undo(self):
        history=History({'value':0});state={'value':10};history.mark_saved(state);state['value']=20
        self.assertFalse(history.dirty({'value':10}));self.assertTrue(history.dirty(state))
        for i in range(100):history.record({'value':i})
        self.assertEqual(history.saved,{'value':10})
        history.mark_saved({'value':99});previous=history.undo({'value':99})
        self.assertTrue(history.dirty(previous));self.assertFalse(history.dirty(history.redo(previous)))

    def test_history_is_bounded(self):
        history=History(0)
        for i in range(100):history.record(i)
        self.assertEqual(len(history.past),50)
