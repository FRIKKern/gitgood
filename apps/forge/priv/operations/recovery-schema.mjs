// Narrow PostgreSQL 18.4 dump/reparse differences observed in Gitgood's native schema.
// Values, bounds, names, operators and all other DDL remain part of the fingerprint.
const literal="'(?:[^']|'')*'::character varying"
const arrayCast=new RegExp("\\(ARRAY\\[((?:"+literal+")(?:, "+literal+")*)\\]\\)::text\\[\\]",'g')
const values=new RegExp(literal,'g')
export function normalizeSchemaLine(line){
  return line.replace(arrayCast,(_,list)=>'ARRAY['+list.match(values).map(value=>'('+value+')::text').join(', ')+']')
    .replaceAll('((size >= 1) AND (size <= 16777216))','(size >= 1) AND (size <= 16777216)')
}
