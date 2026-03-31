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

"""Tests for langextract.core.exceptions."""

from absl.testing import absltest
from absl.testing import parameterized

from langextract.core import exceptions


class ExceptionHierarchyTest(parameterized.TestCase):

  @parameterized.parameters(
      exceptions.InferenceError,
      exceptions.InferenceConfigError,
      exceptions.InferenceRuntimeError,
      exceptions.InferenceOutputError,
      exceptions.InvalidDocumentError,
      exceptions.InternalError,
      exceptions.ProviderError,
      exceptions.SchemaError,
      exceptions.FormatError,
      exceptions.FormatParseError,
  )
  def test_all_inherit_from_langextract_error(self, exc_class):
    self.assertTrue(issubclass(exc_class, exceptions.LangExtractError))

  @parameterized.parameters(
      exceptions.InferenceConfigError,
      exceptions.InferenceRuntimeError,
  )
  def test_inference_subclasses(self, exc_class):
    self.assertTrue(issubclass(exc_class, exceptions.InferenceError))

  def test_format_parse_error_inherits_format_error(self):
    self.assertTrue(
        issubclass(exceptions.FormatParseError, exceptions.FormatError)
    )

  def test_langextract_error_is_exception(self):
    self.assertTrue(issubclass(exceptions.LangExtractError, Exception))


class InferenceRuntimeErrorTest(absltest.TestCase):

  def test_message(self):
    err = exceptions.InferenceRuntimeError('test message')
    self.assertEqual(str(err), 'test message')

  def test_original_and_provider(self):
    original = ValueError('original')
    err = exceptions.InferenceRuntimeError(
        'fail', original=original, provider='gemini'
    )
    self.assertIs(err.original, original)
    self.assertEqual(err.provider, 'gemini')

  def test_defaults(self):
    err = exceptions.InferenceRuntimeError('msg')
    self.assertIsNone(err.original)
    self.assertIsNone(err.provider)

  def test_catchable_as_langextract_error(self):
    with self.assertRaises(exceptions.LangExtractError):
      raise exceptions.InferenceRuntimeError('test')


class InferenceOutputErrorTest(absltest.TestCase):

  def test_message_attribute(self):
    err = exceptions.InferenceOutputError('no outputs')
    self.assertEqual(err.message, 'no outputs')
    self.assertEqual(str(err), 'no outputs')


class RaiseAndCatchTest(parameterized.TestCase):

  @parameterized.named_parameters(
      ('config', exceptions.InferenceConfigError, 'bad config'),
      ('runtime', exceptions.InferenceRuntimeError, 'api fail'),
      ('output', exceptions.InferenceOutputError, 'empty'),
      ('document', exceptions.InvalidDocumentError, 'bad doc'),
      ('internal', exceptions.InternalError, 'bug'),
      ('provider', exceptions.ProviderError, 'backend'),
      ('schema', exceptions.SchemaError, 'bad schema'),
      ('format', exceptions.FormatError, 'bad format'),
      ('format_parse', exceptions.FormatParseError, 'parse fail'),
  )
  def test_raise_and_catch(self, exc_class, msg):
    with self.assertRaises(exc_class) as ctx:
      raise exc_class(msg)
    self.assertIn(msg, str(ctx.exception))


if __name__ == '__main__':
  absltest.main()
