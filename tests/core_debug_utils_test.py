# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for langextract.core.debug_utils."""

import logging

from absl.testing import absltest
from absl.testing import parameterized

from langextract.core import debug_utils


class SafeReprTest(absltest.TestCase):

  def test_short_string(self):
    result = debug_utils._safe_repr('hello')
    self.assertIn('hello', result)

  def test_long_string_truncated(self):
    long_str = 'x' * 1000
    result = debug_utils._safe_repr(long_str)
    self.assertLess(len(result), 1000)

  def test_list_truncated(self):
    big_list = list(range(100))
    result = debug_utils._safe_repr(big_list)
    # Should not contain all 100 items
    self.assertNotIn('99', result)


class RedactValueTest(parameterized.TestCase):

  @parameterized.parameters(
      'api_key', 'apikey', 'token', 'secret', 'password',
      'authorization', 'bearer', 'jwt',
  )
  def test_sensitive_keys_redacted(self, key):
    result = debug_utils._redact_value(key, 'my-secret-value')
    self.assertEqual(result, '<REDACTED>')

  def test_case_insensitive_redaction(self):
    self.assertEqual(
        debug_utils._redact_value('API_KEY', 'val'), '<REDACTED>'
    )

  def test_non_sensitive_key(self):
    result = debug_utils._redact_value('model_name', 'gemini')
    self.assertIn('gemini', result)

  def test_nested_mapping_redacts_sensitive_keys(self):
    mapping = {'api_key': 'secret123', 'model': 'gemini'}
    result = debug_utils._redact_value('config', mapping)
    self.assertIn('<REDACTED>', result)
    self.assertNotIn('secret123', result)
    self.assertIn('gemini', result)

  def test_nested_mapping_preserves_safe_keys(self):
    mapping = {'name': 'test', 'value': 42}
    result = debug_utils._redact_value('config', mapping)
    self.assertIn('test', result)


class RedactMappingTest(absltest.TestCase):

  def test_redacts_sensitive_keys(self):
    result = debug_utils._redact_mapping({
        'api_key': 'secret',
        'model': 'gemini',
    })
    self.assertEqual(result['api_key'], '<REDACTED>')
    self.assertIn('gemini', result['model'])

  def test_empty_mapping(self):
    result = debug_utils._redact_mapping({})
    self.assertEqual(result, {})


class FormatBoundArgsTest(absltest.TestCase):

  def test_simple_function(self):
    def func(a, b):
      pass
    result = debug_utils._format_bound_args(func, (1, 2), {})
    self.assertIn('a=', result)
    self.assertIn('b=', result)

  def test_sensitive_kwarg_redacted(self):
    def func(api_key=''):
      pass
    result = debug_utils._format_bound_args(func, (), {'api_key': 'secret'})
    self.assertIn('<REDACTED>', result)
    self.assertNotIn('secret', result)

  def test_self_replaced_with_type(self):
    class MyClass:
      def method(self, x):
        pass
    obj = MyClass()
    result = debug_utils._format_bound_args(
        MyClass.method, (obj, 42), {}
    )
    self.assertIn('MyClass', result)

  def test_fallback_on_binding_failure(self):
    # Lambda with *args can cause issues - just ensure no crash
    def func(*args, **kwargs):
      pass
    result = debug_utils._format_bound_args(func, (1, 2), {'x': 3})
    self.assertIsInstance(result, str)


class DebugLogCallsTest(absltest.TestCase):

  def test_decorator_preserves_function_name(self):
    @debug_utils.debug_log_calls
    def my_func():
      return 42
    self.assertEqual(my_func.__name__, 'my_func')

  def test_returns_correct_result_without_debug(self):
    @debug_utils.debug_log_calls
    def add(a, b):
      return a + b
    self.assertEqual(add(1, 2), 3)

  def test_reraises_exceptions(self):
    @debug_utils.debug_log_calls
    def failing():
      raise ValueError('boom')

    with self.assertRaises(ValueError) as ctx:
      failing()
    self.assertIn('boom', str(ctx.exception))

  def test_logs_when_debug_enabled(self):
    logger = logging.getLogger('langextract.debug')
    original_level = logger.level

    try:
      logger.setLevel(logging.DEBUG)
      handler = logging.StreamHandler()
      handler.setLevel(logging.DEBUG)
      logger.addHandler(handler)

      @debug_utils.debug_log_calls
      def greet(name):
        return f'hi {name}'

      result = greet('Alice')
      self.assertEqual(result, 'hi Alice')
    finally:
      logger.setLevel(original_level)
      logger.removeHandler(handler)


class ConfigureDebugLoggingTest(absltest.TestCase):

  def test_idempotent(self):
    # Calling twice should not add duplicate handlers
    debug_utils.configure_debug_logging()
    logger = logging.getLogger('langextract')
    count1 = len(logger.handlers)
    debug_utils.configure_debug_logging()
    count2 = len(logger.handlers)
    self.assertEqual(count1, count2)

  def test_sets_debug_level(self):
    debug_utils.configure_debug_logging()
    logger = logging.getLogger('langextract')
    self.assertEqual(logger.level, logging.DEBUG)


if __name__ == '__main__':
  absltest.main()
