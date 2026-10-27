import unittest

from audit_coreless_delivery import browser_success,completed


class CorelessDeliveryAuditTest(unittest.TestCase):
    def test_terminal_success_requires_actual_integer_zero(self):
        completed({'status':'completed','exit_code':0})
        for value in [{'status':'running','exit_code':0},{'status':'timeout'},{'status':'completed','exit_code':False},{'status':'completed','exit_code':None}]:
            with self.assertRaises(ValueError):completed(value)

    def test_empty_skipped_flaky_or_expected_failure_browser_results_are_not_accepted(self):
        for stats in [{'expected':0},{'expected':1,'skipped':1},{'expected':1,'flaky':1},{'expected':1,'unexpected':1}]:
            with self.assertRaises(ValueError):browser_success({'stats':stats,'suites':[]})
        with self.assertRaises(ValueError):
            browser_success({'stats':{'expected':1},'suites':[{'specs':[{'tests':[{'expectedStatus':'failed','results':[{'status':'failed'}]}]}]}]})

    def test_regular_passed_browser_result_is_accepted(self):
        browser_success({'stats':{'expected':1},'suites':[{'specs':[{'tests':[{'expectedStatus':'passed','results':[{'status':'passed'}]}]}]}]})
