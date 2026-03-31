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

"""Tests for langextract.core.base_model."""

from collections.abc import Iterator, Sequence
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized

from langextract.core import base_model
from langextract.core import schema
from langextract.core import types


class _FakeModel(base_model.BaseLanguageModel):
  """Minimal concrete subclass for testing."""

  def __init__(self, results=None, **kwargs):
    super().__init__(**kwargs)
    self._results = results or []

  def infer(
      self, batch_prompts: Sequence[str], **kwargs
  ) -> Iterator[Sequence[types.ScoredOutput]]:
    for r in self._results:
      yield r


class BaseLanguageModelInitTest(absltest.TestCase):

  def test_default_constraint(self):
    model = _FakeModel()
    self.assertEqual(
        model._constraint.constraint_type, types.ConstraintType.NONE
    )

  def test_explicit_constraint(self):
    c = types.Constraint(constraint_type=types.ConstraintType.NONE)
    model = _FakeModel(constraint=c)
    self.assertIs(model._constraint, c)

  def test_none_constraint_creates_default(self):
    model = _FakeModel(constraint=None)
    self.assertIsNotNone(model._constraint)
    self.assertEqual(
        model._constraint.constraint_type, types.ConstraintType.NONE
    )

  def test_extra_kwargs_stored(self):
    model = _FakeModel(temperature=0.5, max_tokens=100)
    self.assertEqual(model._extra_kwargs, {'temperature': 0.5, 'max_tokens': 100})

  def test_abstract_cannot_instantiate(self):
    with self.assertRaises(TypeError):
      base_model.BaseLanguageModel()


class SchemaTest(absltest.TestCase):

  def test_schema_default_none(self):
    model = _FakeModel()
    self.assertIsNone(model.schema)

  def test_apply_and_get_schema(self):
    model = _FakeModel()
    mock_schema = mock.create_autospec(schema.BaseSchema, instance=True)
    model.apply_schema(mock_schema)
    self.assertIs(model.schema, mock_schema)

  def test_clear_schema(self):
    model = _FakeModel()
    mock_schema = mock.create_autospec(schema.BaseSchema, instance=True)
    model.apply_schema(mock_schema)
    model.apply_schema(None)
    self.assertIsNone(model.schema)

  def test_get_schema_class_returns_none(self):
    self.assertIsNone(_FakeModel.get_schema_class())


class FenceOutputTest(absltest.TestCase):

  def test_default_requires_fence_no_schema(self):
    model = _FakeModel()
    self.assertTrue(model.requires_fence_output)

  def test_override_true(self):
    model = _FakeModel()
    model.set_fence_output(True)
    self.assertTrue(model.requires_fence_output)

  def test_override_false(self):
    model = _FakeModel()
    model.set_fence_output(False)
    self.assertFalse(model.requires_fence_output)

  def test_override_none_falls_through(self):
    model = _FakeModel()
    model.set_fence_output(None)
    # No schema -> True
    self.assertTrue(model.requires_fence_output)

  def test_schema_requires_raw_output(self):
    model = _FakeModel()
    mock_schema = mock.create_autospec(schema.BaseSchema, instance=True)
    type(mock_schema).requires_raw_output = mock.PropertyMock(return_value=True)
    model.apply_schema(mock_schema)
    # Schema says raw output -> fence not needed
    self.assertFalse(model.requires_fence_output)

  def test_schema_no_raw_output(self):
    model = _FakeModel()
    mock_schema = mock.create_autospec(schema.BaseSchema, instance=True)
    type(mock_schema).requires_raw_output = mock.PropertyMock(return_value=False)
    model.apply_schema(mock_schema)
    self.assertTrue(model.requires_fence_output)

  def test_override_takes_precedence_over_schema(self):
    model = _FakeModel()
    mock_schema = mock.create_autospec(schema.BaseSchema, instance=True)
    type(mock_schema).requires_raw_output = mock.PropertyMock(return_value=True)
    model.apply_schema(mock_schema)
    model.set_fence_output(True)
    # Override wins
    self.assertTrue(model.requires_fence_output)


class MergeKwargsTest(absltest.TestCase):

  def test_no_runtime_kwargs(self):
    model = _FakeModel(temperature=0.5)
    merged = model.merge_kwargs()
    self.assertEqual(merged, {'temperature': 0.5})

  def test_runtime_kwargs_override(self):
    model = _FakeModel(temperature=0.5)
    merged = model.merge_kwargs({'temperature': 0.9, 'top_p': 0.8})
    self.assertEqual(merged, {'temperature': 0.9, 'top_p': 0.8})

  def test_none_runtime_kwargs(self):
    model = _FakeModel(temperature=0.5)
    merged = model.merge_kwargs(None)
    self.assertEqual(merged, {'temperature': 0.5})

  def test_no_stored_kwargs(self):
    model = _FakeModel()
    merged = model.merge_kwargs({'top_k': 10})
    self.assertEqual(merged, {'top_k': 10})

  def test_missing_extra_kwargs_attr(self):
    model = _FakeModel()
    del model._extra_kwargs
    merged = model.merge_kwargs({'x': 1})
    self.assertEqual(merged, {'x': 1})


class InferBatchTest(absltest.TestCase):

  def test_collects_results(self):
    out1 = [types.ScoredOutput(score=0.9, output='a')]
    out2 = [types.ScoredOutput(score=0.8, output='b')]
    model = _FakeModel(results=[out1, out2])
    results = model.infer_batch(['prompt1', 'prompt2'])
    self.assertLen(results, 2)
    self.assertEqual(results[0], out1)
    self.assertEqual(results[1], out2)

  def test_empty_results(self):
    model = _FakeModel(results=[])
    results = model.infer_batch([])
    self.assertEmpty(results)


class ParseOutputTest(parameterized.TestCase):

  def test_parse_json(self):
    model = _FakeModel()
    result = model.parse_output('{"key": "value"}')
    self.assertEqual(result, {'key': 'value'})

  def test_parse_json_list(self):
    model = _FakeModel()
    result = model.parse_output('[1, 2, 3]')
    self.assertEqual(result, [1, 2, 3])

  def test_parse_yaml(self):
    model = _FakeModel()
    model.format_type = types.FormatType.YAML
    result = model.parse_output('key: value\n')
    self.assertEqual(result, {'key': 'value'})

  def test_invalid_json_raises(self):
    model = _FakeModel()
    with self.assertRaises(ValueError) as ctx:
      model.parse_output('not valid json')
    self.assertIn('JSON', str(ctx.exception))

  def test_invalid_yaml_raises(self):
    model = _FakeModel()
    model.format_type = types.FormatType.YAML
    with self.assertRaises(ValueError):
      model.parse_output(':\n  :\n    - ][')


if __name__ == '__main__':
  absltest.main()
