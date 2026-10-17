#!/usr/bin/env python3
"""Portable source-transform checks; these do not establish compiler behavior."""
import ast
import builtins
from pathlib import Path
import sys
import tokenize
import io
import unittest

sys.dont_write_bytecode=True
import path_body_source as source


def transformed(text,globals_dict):
    generated,count=source.redirect_globals(ast.parse(text))
    missing=object();builtin_dict=vars(builtins)
    def lookup(name):
        value=globals_dict.get(name,missing)
        if value is missing:value=builtin_dict.get(name,missing)
        if value is missing:raise NameError("name "+repr(name)+" is not defined",name=name)
        return value
    namespace={source.LOOKUP:lookup}
    exec(compile(generated,'<synthetic-path-body>','exec'),namespace)
    return namespace,count


class LiveGlobalSourceTest(unittest.TestCase):
    def test_live_rebinding_and_builtin_shadowing_are_not_snapshotted(self):
        text='class Model:\n def read(self,x): return convert(x)+offset\n'
        values={'convert':lambda value:value*2,'offset':1}
        namespace,count=transformed(text,values);model=namespace['Model']()
        self.assertEqual(model.read(3),7);self.assertEqual(count,2)
        values['offset']=9;values['convert']=lambda value:value+4
        self.assertEqual(model.read(3),16)

    def test_local_free_and_nested_default_bindings_remain_lexical(self):
        text='''class Model:
 def read(self,value):
  offset=value
  def inner(item=3):
   return item+offset+external
  return inner()
'''
        namespace,_=transformed(text,{'external':8,'offset':999,'value':999})
        self.assertEqual(namespace['Model']().read(4),15)

    def test_comprehension_first_iterable_uses_outer_binding_and_later_iterables_use_local_target(self):
        text='''class Model:
 def read(self,items):
  return [(items,value+shift) for items in items for value in range(items) if allowed(value)]
'''
        values={'shift':10,'allowed':lambda value:value%2==0,'items':999}
        namespace,_=transformed(text,values)
        self.assertEqual(namespace['Model']().read([1,3]),[(1,10),(3,10),(3,12)])

    def test_lambda_generator_set_and_dictionary_comprehensions_keep_nested_scopes(self):
        text='''class Model:
 def read(self,values):
  apply=lambda item: item+shift
  return ({apply(item) for item in values}, {item:apply(item) for item in values}, tuple(apply(item) for item in values))
'''
        namespace,_=transformed(text,{'shift':4})
        self.assertEqual(namespace['Model']().read([1,2]),({5,6},{1:5,2:6},(5,6)))

    def test_comprehension_target_shadows_global_only_inside_and_does_not_leak(self):
        text='class Model:\n def read(self): return [item for item in item],item\n'
        values={'item':[1,2]};namespace,_=transformed(text,values)
        self.assertEqual(namespace['Model']().read(),([1,2],[1,2]))
        values['item']=[3];self.assertEqual(namespace['Model']().read(),([3],[3]))

    def test_later_assignment_keeps_unbound_local_error_instead_of_reading_global(self):
        text='class Model:\n def read(self):\n  value=local\n  local=4\n  return value\n'
        namespace,_=transformed(text,{'local':999})
        with self.assertRaises(UnboundLocalError):namespace['Model']().read()

    def test_original_class_reference_and_classmethod_property_descriptors_keep_original_receivers(self):
        text='''class Model:
 @classmethod
 def parse(cls,value): return cls.label+str(value)
 @property
 def name(self): return type(self).label
 def make(self): return Original()
'''
        class Original:label='original'
        namespace,_=transformed(text,{'Original':Original});donor=namespace['Model']
        original_parse=Original.__dict__.get('parse')
        self.assertIsNone(original_parse)
        Original.parse=vars(donor)['parse'];Original.name=vars(donor)['name'];Original.make=vars(donor)['make']
        self.assertEqual(Original.parse(3),'original3');self.assertEqual(Original().name,'original')
        self.assertIs(type(Original().make()),Original)

    def test_missing_global_and_python_builtin_resolution_keep_name_error_type_and_arguments(self):
        text='class Model:\n def read(self): return missing_name\n'
        namespace,_=transformed(text,{})
        with self.assertRaises(NameError) as caught:namespace['Model']().read()
        self.assertEqual(caught.exception.args,("name 'missing_name' is not defined",))
        self.assertEqual(caught.exception.name,'missing_name')
        self.assertIsNone(caught.exception.__context__)
        namespace,_=transformed('class Model:\n def read(self): return str(4)\n',{'str':lambda value:'shadow'})
        self.assertEqual(namespace['Model']().read(),'shadow')

    def test_selector_is_closed_and_refuses_class_closure_or_unsupported_decorators(self):
        text='\n'.join('class '+owner+':\n'+'\n'.join(' def '+name+'(self): return global_value'
            for name in names) for owner,names in source.TARGETS.items())
        generated,manifest=source.select_source(text)
        self.assertEqual(len(manifest['bodies']),20);self.assertFalse(manifest['compiled'])
        self.assertFalse(manifest['original_classes_replaced'])
        self.assertEqual(manifest['live_global_loads'],20)
        for bad in [text.replace('return global_value','return super()',1),
                text.replace(' def __init__',' @unknown\n def __init__',1),
                text.replace('def __init__(self)','def __init__(self: int)',1),
                text.replace(' def __init__',' def missing',1)]:
            with self.assertRaises(ValueError):source.select_source(bad)

    def test_source_bounds_and_nonliteral_defaults_refuse_before_execution(self):
        for raw in ['', ' '*262145, object()]:
            with self.assertRaises(ValueError):source.select_source(raw)
        tree=ast.parse('class Model:\n def read(self,value=external): return value\n')
        with self.assertRaises(ValueError):source.redirect_globals(tree)

    def test_reserved_lookup_name_cannot_be_shadowed_by_input_bindings(self):
        for text in ['class Model:\n def read(self,_gitgood_path_body_name): return external\n',
                'class Model:\n def read(self): return _gitgood_path_body_name("external")\n',
                'class Model:\n def read(self):\n  import module as _gitgood_path_body_name\n  return external\n']:
            with self.assertRaises(ValueError):source.redirect_globals(ast.parse(text))

    def test_fstring_global_expression_quoting_keeps_exact_exception_arguments(self):
        text='class Model:\n def read(self,item): raise TypeError(f"unsupported {type(item).__name__!r}")\n'
        generated,_=source.redirect_globals(ast.parse(text))
        starts=[item.string for item in tokenize.generate_tokens(io.StringIO(generated).readline)
            if item.type==tokenize.FSTRING_START]
        self.assertEqual(starts,['f"""'])
        namespace,_=transformed(text,{})
        with self.assertRaises(TypeError) as caught:namespace['Model']().read(7)
        self.assertEqual(caught.exception.args,("unsupported 'int'",))

    def test_nested_fstrings_format_specs_and_escapes_keep_original_values(self):
        text='class Model:\n def read(self,item): return f"outer {f\'inner {type(item).__name__}\'} {item!r:>8} \\n"\n'
        baseline={};exec(text,baseline)
        generated,_=source.redirect_globals(ast.parse(text))
        starts=[item.string for item in tokenize.generate_tokens(io.StringIO(generated).readline)
            if item.type==tokenize.FSTRING_START]
        self.assertEqual(starts,['f"""',"f'''"])
        namespace,_=transformed(text,{})
        self.assertEqual(namespace['Model']().read(7),baseline['Model']().read(7))


if __name__=='__main__':unittest.main(verbosity=2)
