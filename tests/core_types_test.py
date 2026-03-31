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

"""Tests for langextract.core.types."""

from absl.testing import absltest
from absl.testing import parameterized

from langextract.core import types


class FormatTypeTest(absltest.TestCase):

  def test_yaml_value(self):
    self.assertEqual(types.FormatType.YAML.value, 'yaml')

  def test_json_value(self):
    self.assertEqual(types.FormatType.JSON.value, 'json')

  def test_members(self):
    self.assertCountEqual(
        [m.name for m in types.FormatType], ['YAML', 'JSON']
    )


class ConstraintTypeTest(absltest.TestCase):

  def test_none_value(self):
    self.assertEqual(types.ConstraintType.NONE.value, 'none')


class ConstraintTest(absltest.TestCase):

  def test_default_constraint_type(self):
    c = types.Constraint()
    self.assertEqual(c.constraint_type, types.ConstraintType.NONE)

  def test_explicit_constraint_type(self):
    c = types.Constraint(constraint_type=types.ConstraintType.NONE)
    self.assertEqual(c.constraint_type, types.ConstraintType.NONE)


class ScoredOutputTest(parameterized.TestCase):

  def test_defaults(self):
    so = types.ScoredOutput()
    self.assertIsNone(so.score)
    self.assertIsNone(so.output)

  def test_with_values(self):
    so = types.ScoredOutput(score=0.95, output='hello')
    self.assertEqual(so.score, 0.95)
    self.assertEqual(so.output, 'hello')

  def test_frozen(self):
    so = types.ScoredOutput(score=1.0, output='test')
    with self.assertRaises(AttributeError):
      so.score = 2.0

  def test_str_none_score_none_output(self):
    so = types.ScoredOutput()
    result = str(so)
    self.assertIn('Score: -', result)
    self.assertIn('Output: None', result)

  def test_str_with_score_none_output(self):
    so = types.ScoredOutput(score=0.5)
    result = str(so)
    self.assertIn('Score: 0.50', result)
    self.assertIn('Output: None', result)

  def test_str_none_score_with_output(self):
    so = types.ScoredOutput(output='hello world')
    result = str(so)
    self.assertIn('Score: -', result)
    self.assertIn('hello world', result)
    self.assertNotIn('Output: None', result)

  def test_str_with_score_and_output(self):
    so = types.ScoredOutput(score=0.123, output='result text')
    result = str(so)
    self.assertIn('Score: 0.12', result)
    self.assertIn('result text', result)

  def test_str_multiline_output_indented(self):
    so = types.ScoredOutput(score=1.0, output='line1\nline2')
    result = str(so)
    self.assertIn('  line1', result)
    self.assertIn('  line2', result)

  def test_equality(self):
    a = types.ScoredOutput(score=1.0, output='x')
    b = types.ScoredOutput(score=1.0, output='x')
    self.assertEqual(a, b)

  def test_inequality(self):
    a = types.ScoredOutput(score=1.0, output='x')
    b = types.ScoredOutput(score=2.0, output='x')
    self.assertNotEqual(a, b)


if __name__ == '__main__':
  absltest.main()
