import test from 'node:test'
import assert from 'node:assert/strict'
import {normalizeSchemaLine} from '../../priv/operations/recovery-schema.mjs'

test('evidence-bound dump reparsing retains every constraint term and refuses semantic differences',()=>{
 const original='    CONSTRAINT criterion_evidence_bounds CHECK ((((criterion_index >= 0) AND (criterion_index <= 99)) AND ((artifact_size >= 1) AND (artifact_size <= 65536)) AND (artifact_size = octet_length(artifact_content)) AND (octet_length(request_digest) = 32))),'
 const restored='    CONSTRAINT criterion_evidence_bounds CHECK (((criterion_index >= 0) AND (criterion_index <= 99) AND ((artifact_size >= 1) AND (artifact_size <= 65536)) AND (artifact_size = octet_length(artifact_content)) AND (octet_length(request_digest) = 32))),'
 assert.equal(normalizeSchemaLine(original),normalizeSchemaLine(restored))
 for(const [before,after] of [['<= 99','<= 100'],['>= 0','>= -1'],['<= 65536','<= 65537'],['= 32','= 31'],[' AND ',' OR '],['criterion_evidence_bounds','other_constraint'],['artifact_size =','artifact_size <>']])
  assert.notEqual(normalizeSchemaLine(original.replace(before,after)),normalizeSchemaLine(restored))
 const unrelated="SELECT '"+original+"';"
 assert.equal(normalizeSchemaLine(unrelated),unrelated)
})
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
