import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

from native_monitor_ownership_attachment import MonitorOwnershipAttachment
from resource_generations import canonical


class MonitorOwnershipAttachmentTest(unittest.TestCase):
    def setUp(self):
        self.guard=SimpleNamespace(check=Mock(return_value={'current':True}),close=Mock())
        self.captured={'original':'capture'};self.seal={'original':'seal'}
        self.subject=MonitorOwnershipAttachment(self.guard,self.captured,self.seal)
        value={'current':{'current':True},'ownership':{'original':True}}
        self.observer=SimpleNamespace(take_initial=Mock(return_value=value),check=Mock(return_value=value),close=Mock())
        self.factory=patch('native_monitor_ownership_attachment.NativeOwnershipObservation',return_value=self.observer).start()
        self.addCleanup(patch.stopall);self.addCleanup(self.subject.close)
        self.message=canonical({'protocol':2,'action':'attach_ownership','record':{'fixture':'record'}})+b'\n'

    def test_partial_frame_attaches_only_original_guard_and_capture(self):
        self.assertIsNone(self.subject.feed(self.message[:12]));self.factory.assert_not_called()
        self.assertEqual(self.subject.check(),{'current':{'current':True}})
        result=self.subject.feed(self.message[12:])
        self.factory.assert_called_once_with(self.guard,self.captured,{'fixture':'record'},self.seal)
        self.observer.take_initial.assert_called_once_with()
        self.observer.check.assert_not_called()
        self.assertEqual(result,self.subject.check())
        self.observer.check.assert_called_once_with()
        self.guard.close.assert_not_called()

    def test_second_attachment_or_trailing_frame_permanently_refuses(self):
        self.subject.feed(self.message)
        with self.assertRaises(ValueError):self.subject.feed(self.message)
        self.observer.close.assert_called_once();self.assertTrue(self.subject.poisoned)
        with self.assertRaises(ValueError):self.subject.check()
        self.factory.assert_called_once()

    def test_extra_bytes_before_attachment_refuse_without_observer(self):
        with self.assertRaises(ValueError):self.subject.feed(self.message+b'x')
        self.factory.assert_not_called();self.assertTrue(self.subject.poisoned)

    def test_noncanonical_duplicate_extra_or_wrong_action_refuse(self):
        for raw in [b'{"protocol":2,"protocol":2,"action":"attach_ownership","record":{}}\n',
                    canonical({'protocol':True,'action':'attach_ownership','record':{}})+b'\n',
                    canonical({'protocol':2,'action':'replace_owner','record':{}})+b'\n',
                    canonical({'protocol':2,'action':'attach_ownership','record':{},'grant':True})+b'\n',
                    self.message.replace(b':',b': ',1)]:
            subject=MonitorOwnershipAttachment(self.guard,self.captured,self.seal)
            with self.assertRaises(ValueError):subject.feed(raw)
            self.assertTrue(subject.poisoned)
        self.factory.assert_not_called()

    def test_empty_and_oversized_input_refuse_before_construction(self):
        for raw in [b'',b'x'*20_001]:
            subject=MonitorOwnershipAttachment(self.guard,self.captured,self.seal)
            with self.assertRaises(ValueError):subject.feed(raw)
            self.assertTrue(subject.poisoned)
        self.factory.assert_not_called()

    def test_observer_loss_is_terminal_and_original_guard_remains_caller_owned(self):
        self.subject.feed(self.message)
        self.observer.check.side_effect=ValueError('lost')
        with self.assertRaises(ValueError):self.subject.check()
        self.observer.close.assert_called_once()
        with self.assertRaises(ValueError):self.subject.check()
        self.guard.close.assert_not_called()

    def test_construction_loss_permanently_refuses_without_recapture(self):
        self.factory.side_effect=ValueError('lost')
        with self.assertRaises(ValueError):self.subject.feed(self.message)
        with self.assertRaises(ValueError):self.subject.feed(self.message)
        self.factory.assert_called_once();self.guard.close.assert_not_called()


if __name__=='__main__':unittest.main()
