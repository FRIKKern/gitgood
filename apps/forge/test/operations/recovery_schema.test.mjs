import test from 'node:test'
import assert from 'node:assert/strict'
import {normalizeSchemaLine} from '../../priv/operations/recovery-schema.mjs'
const source="CONSTRAINT role_allowed CHECK (((role)::text = ANY ((ARRAY['owner'::character varying, 'writer'::character varying, 'reader'::character varying])::text[])));"
const restored="CONSTRAINT role_allowed CHECK (((role)::text = ANY (ARRAY[('owner'::character varying)::text, ('writer'::character varying)::text, ('reader'::character varying)::text])));"
test('known varchar array cast reparse preserves every literal',()=>{
 assert.equal(normalizeSchemaLine(source),restored)
 assert.equal(normalizeSchemaLine(restored),restored)
 assert.notEqual(normalizeSchemaLine(source.replace("'reader'","'outsider'")),restored)
 assert.notEqual(normalizeSchemaLine(source.replace('role_allowed','other_constraint')),restored)
 assert.notEqual(normalizeSchemaLine(source.replace(' = ANY',' <> ALL')),restored)
})
test('only the exact native asset bound grouping is flattened',()=>{
 const before='CHECK ((((size >= 1) AND (size <= 16777216)) AND valid));'
 const after='CHECK (((size >= 1) AND (size <= 16777216) AND valid));'
 assert.equal(normalizeSchemaLine(before),after)
 assert.notEqual(normalizeSchemaLine(before.replace('16777216','16777217')),after)
 assert.notEqual(normalizeSchemaLine(before.replace('AND valid','OR valid')),after)
 assert.equal(normalizeSchemaLine('((other >= 1) AND (other <= 16777216))'),'((other >= 1) AND (other <= 16777216))')
})
