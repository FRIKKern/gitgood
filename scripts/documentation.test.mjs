import test from 'node:test'
import assert from 'node:assert/strict'
import {documentationProblems} from './documentation.mjs'

const fixture = () => ({
  'docs/README.md': '[Getting started](DEVELOPMENT.md) · [Code map](CODEBASE.md#forge)',
  'docs/DEVELOPMENT.md': '# Development',
  'docs/CODEBASE.md': '# Code map',
  'docs/implementation/README.md': '[Private browsing](browsing.md)',
  'docs/implementation/browsing.md': '# Browsing',
  'docs/decisions/README.md': '[Identity](0002-local-identity.md)',
  'docs/decisions/0002-local-identity.md': '# Identity'
})

test('new reference documents must be discoverable from their own index', () => {
  const docs = fixture()
  docs['docs/implementation/recovery.md'] = '# Recovery'
  assert.deepEqual(documentationProblems(Object.keys(docs), name => docs[name]), [
    'Unindexed document: docs/implementation/recovery.md; add a descriptive link in docs/implementation/README.md'
  ])
  docs['docs/implementation/README.md'] += '\n[Recovery](recovery.md#restore)'
  assert.deepEqual(documentationProblems(Object.keys(docs), name => docs[name]), [])
})

test('external links and a different directory do not accidentally index a document', () => {
  const docs = fixture()
  docs['docs/implementation/README.md'] = '[Example](https://example.test/browsing.md) [Other](../browsing.md)'
  assert.equal(documentationProblems(Object.keys(docs), name => docs[name]).length, 1)
})

test('navigation accepts Windows file names and fails a missing portal', () => {
  const docs = fixture()
  assert.deepEqual(documentationProblems(Object.keys(docs).map(name => name.replaceAll('/', '\\')), name => docs[name]), [])
  delete docs['docs/README.md']
  assert.deepEqual(documentationProblems(Object.keys(docs), name => docs[name]), ['Missing documentation index: docs/README.md'])
})
