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

"""Tests for langextract.core.data."""

from unittest import mock

from absl.testing import absltest

from langextract.core import data
from langextract.core import tokenizer
from langextract.core import types


class ConstantsTest(absltest.TestCase):

  def test_extractions_key(self):
    self.assertEqual(data.EXTRACTIONS_KEY, 'extractions')

  def test_attribute_suffix(self):
    self.assertEqual(data.ATTRIBUTE_SUFFIX, '_attributes')

  def test_format_type_backward_compat(self):
    self.assertIs(data.FormatType, types.FormatType)


class AlignmentStatusTest(absltest.TestCase):

  def test_values(self):
    self.assertEqual(data.AlignmentStatus.MATCH_EXACT.value, 'match_exact')
    self.assertEqual(data.AlignmentStatus.MATCH_GREATER.value, 'match_greater')
    self.assertEqual(data.AlignmentStatus.MATCH_LESSER.value, 'match_lesser')
    self.assertEqual(data.AlignmentStatus.MATCH_FUZZY.value, 'match_fuzzy')


class CharIntervalTest(absltest.TestCase):

  def test_defaults(self):
    ci = data.CharInterval()
    self.assertIsNone(ci.start_pos)
    self.assertIsNone(ci.end_pos)

  def test_with_values(self):
    ci = data.CharInterval(start_pos=5, end_pos=10)
    self.assertEqual(ci.start_pos, 5)
    self.assertEqual(ci.end_pos, 10)


class ExtractionTest(absltest.TestCase):

  def test_required_fields(self):
    e = data.Extraction('PERSON', 'Alice')
    self.assertEqual(e.extraction_class, 'PERSON')
    self.assertEqual(e.extraction_text, 'Alice')

  def test_optional_fields_default_none(self):
    e = data.Extraction('LOC', 'Paris')
    self.assertIsNone(e.char_interval)
    self.assertIsNone(e.alignment_status)
    self.assertIsNone(e.extraction_index)
    self.assertIsNone(e.group_index)
    self.assertIsNone(e.description)
    self.assertIsNone(e.attributes)
    self.assertIsNone(e.token_interval)

  def test_all_kwargs(self):
    ti = tokenizer.TokenInterval(start_index=0, end_index=3)
    ci = data.CharInterval(start_pos=0, end_pos=5)
    e = data.Extraction(
        'ORG',
        'Google',
        token_interval=ti,
        char_interval=ci,
        alignment_status=data.AlignmentStatus.MATCH_EXACT,
        extraction_index=0,
        group_index=1,
        description='company',
        attributes={'type': 'tech'},
    )
    self.assertEqual(e.extraction_class, 'ORG')
    self.assertEqual(e.extraction_text, 'Google')
    self.assertIs(e.token_interval, ti)
    self.assertIs(e.char_interval, ci)
    self.assertEqual(e.alignment_status, data.AlignmentStatus.MATCH_EXACT)
    self.assertEqual(e.extraction_index, 0)
    self.assertEqual(e.group_index, 1)
    self.assertEqual(e.description, 'company')
    self.assertEqual(e.attributes, {'type': 'tech'})

  def test_token_interval_property_setter(self):
    e = data.Extraction('X', 'y')
    self.assertIsNone(e.token_interval)
    ti = tokenizer.TokenInterval(start_index=1, end_index=5)
    e.token_interval = ti
    self.assertIs(e.token_interval, ti)

  def test_token_interval_not_in_repr(self):
    ti = tokenizer.TokenInterval(start_index=0, end_index=1)
    e = data.Extraction('X', 'y', token_interval=ti)
    self.assertNotIn('token_interval', repr(e))
    self.assertNotIn('_token_interval', repr(e))


class DocumentTest(absltest.TestCase):

  def test_basic_creation(self):
    doc = data.Document('Hello world')
    self.assertEqual(doc.text, 'Hello world')
    self.assertIsNone(doc.additional_context)

  def test_with_additional_context(self):
    doc = data.Document('text', additional_context='context')
    self.assertEqual(doc.additional_context, 'context')

  def test_auto_generated_id(self):
    doc = data.Document('text')
    doc_id = doc.document_id
    self.assertTrue(doc_id.startswith('doc_'))
    self.assertLen(doc_id, 12)  # "doc_" + 8 hex chars

  def test_auto_id_is_stable(self):
    doc = data.Document('text')
    id1 = doc.document_id
    id2 = doc.document_id
    self.assertEqual(id1, id2)

  def test_explicit_document_id(self):
    doc = data.Document('text', document_id='my-doc')
    self.assertEqual(doc.document_id, 'my-doc')

  def test_document_id_setter(self):
    doc = data.Document('text')
    doc.document_id = 'custom-id'
    self.assertEqual(doc.document_id, 'custom-id')

  def test_lazy_tokenization(self):
    doc = data.Document('Hello world')
    # Access tokenized_text triggers tokenization
    tt = doc.tokenized_text
    self.assertIsInstance(tt, tokenizer.TokenizedText)
    self.assertEqual(tt.text, 'Hello world')

  def test_tokenized_text_cached(self):
    doc = data.Document('Hello')
    tt1 = doc.tokenized_text
    tt2 = doc.tokenized_text
    self.assertIs(tt1, tt2)

  def test_tokenized_text_setter(self):
    doc = data.Document('Hello')
    custom_tt = tokenizer.TokenizedText(text='Hello', tokens=[])
    doc.tokenized_text = custom_tt
    self.assertIs(doc.tokenized_text, custom_tt)


class AnnotatedDocumentTest(absltest.TestCase):

  def test_default_creation(self):
    ad = data.AnnotatedDocument()
    self.assertIsNone(ad.extractions)
    self.assertIsNone(ad.text)

  def test_with_extractions(self):
    ext = data.Extraction('PER', 'Bob')
    ad = data.AnnotatedDocument(extractions=[ext])
    self.assertLen(ad.extractions, 1)
    self.assertEqual(ad.extractions[0].extraction_text, 'Bob')

  def test_with_text(self):
    ad = data.AnnotatedDocument(text='Some text')
    self.assertEqual(ad.text, 'Some text')

  def test_auto_generated_id(self):
    ad = data.AnnotatedDocument()
    doc_id = ad.document_id
    self.assertTrue(doc_id.startswith('doc_'))
    self.assertLen(doc_id, 12)

  def test_explicit_document_id(self):
    ad = data.AnnotatedDocument(document_id='ad-1')
    self.assertEqual(ad.document_id, 'ad-1')

  def test_document_id_setter(self):
    ad = data.AnnotatedDocument()
    ad.document_id = 'new-id'
    self.assertEqual(ad.document_id, 'new-id')

  def test_lazy_tokenization_with_text(self):
    ad = data.AnnotatedDocument(text='Hello world')
    tt = ad.tokenized_text
    self.assertIsInstance(tt, tokenizer.TokenizedText)

  def test_tokenization_none_when_no_text(self):
    ad = data.AnnotatedDocument()
    self.assertIsNone(ad.tokenized_text)

  def test_tokenized_text_setter(self):
    ad = data.AnnotatedDocument(text='Hi')
    custom_tt = tokenizer.TokenizedText(text='Hi', tokens=[])
    ad.tokenized_text = custom_tt
    self.assertIs(ad.tokenized_text, custom_tt)

  def test_keyword_only_init(self):
    # AnnotatedDocument uses keyword-only __init__
    ad = data.AnnotatedDocument(
        document_id='x', extractions=[], text='t'
    )
    self.assertEqual(ad.document_id, 'x')


class ExampleDataTest(absltest.TestCase):

  def test_basic_creation(self):
    ed = data.ExampleData(text='sample')
    self.assertEqual(ed.text, 'sample')
    self.assertEqual(ed.extractions, [])

  def test_with_extractions(self):
    ext = data.Extraction('SKILL', 'Python')
    ed = data.ExampleData(text='I know Python', extractions=[ext])
    self.assertLen(ed.extractions, 1)


if __name__ == '__main__':
  absltest.main()
