import json
import re

IDENT_RE = re.compile('[a-zA-Z_][a-zA-Z0-9_]*')
def is_ident(name):
    return bool(IDENT_RE.fullmatch(name))
UNSAFE_CHAR_RE = re.compile('[^a-zA-Z0-9_]')
MULTI_UNDERSCORE_RE = re.compile('_+')
def make_ident(*components):
    name = '_'.join(components)
    name = UNSAFE_CHAR_RE.sub('_', name)
    name = MULTI_UNDERSCORE_RE.sub('_', name)
    if name.endswith('_'):
        name = name[:-1]
    if not name or name[0].isnumeric():
        name = f'_{name}'
    return name

def make_string(contents):
    def escape(c):
        oc = ord(c)
        if (oc >= 32 and oc <= 126) or (oc > 65535):
            return c
        special_escape = {
            '\b': '\\b',
            '\f': '\\f',
            '\n': '\\n',
            '\r': '\\r',
            '\t': '\\t',
        }.get(c, None)
        if special_escape is not None:
            return special_escape
        return f'\\u{oc:04X}'
    contents = ''.join(map(escape, contents))
    return f'"{contents}"'


class MessageUnpacker:
    class Missing:
        pass

    def __init__(self, err_ctxt, obj):
        self.err_ctxt = err_ctxt
        self.obj = obj

    def pop(self, key, typ, default=Missing):
        value = self.obj.pop(key, default)
        if value is self.Missing:
            raise KeyError(f'missing required key {key} in {self.err_ctxt}')
        if not isinstance(value, typ):
            actual = type(value)
            raise KeyError(f'value for key {key} in {self.err_ctxt} is of unexpected type {actual}')
        return value

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.obj:
            raise ValueError('unknown key(s) in {}: {}'.format(self.err_ctxt, ', '.join(self.obj)))


class OneOfMessageUnpacker:
    def __init__(self, err_ctxt, obj):
        self.err_ctxt = err_ctxt
        if len(obj) != 1:
            raise ValueError(f'value for oneof field {self.err_ctxt} must have a single key')
        self.key, self.val = next(iter(obj.items()))
        self.matched = False

    def handle(self, key):
        match = self.key == key
        if match:
            self.matched = True
        return match

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if not self.matched:
            raise ValueError(f'unknown oneof variant for {self.err_ctxt}: {self.key}')


def disas(data):

    # Decode JSON.
    plan = json.loads(data)

    # Unpack toplevel structure.
    with MessageUnpacker('plan', plan) as u:
        extension_uris = u.pop('extensionUris', list, [])
        extensions = u.pop('extensions', list, [])
        relations = u.pop('relations', list, [])
        advanced_extensions = u.pop('advancedExtensions', dict, {})
        expected_type_urls = u.pop('expectedTypeUrls', list, [])

    # Unpack toplevel extension(s?). It's probably not intentional that this is
    # not an array, but let's roll with it for now...
    with MessageUnpacker('toplevel advanced extension object', advanced_extensions) as u:
        toplevel_enhancement = u.pop('enhancement', dict, {})
        toplevel_optimization = u.pop('optimization', dict, {})

    # We'll need unique names to refer to things in the file. These names don't
    # exist in the input JSON, so we'll need to generate them.
    used_names = set()
    def uniquify(name):
        """Returns name, or name_2, or name_3, or name_4 etc. until a name is
        found that isn't in use yet."""
        assert is_ident(name)
        if name not in used_names:
            used_names.add(name)
            return name
        i = 2
        while True:
            uniquified = f'{name}_{i}'
            if uniquified not in used_names:
                used_names.add(uniquified)
                return uniquified
            i += 1

    # Gather statements in a list, then join them later for performance.
    output = []

    # Emit extension declarations. The lookup tables below map anchors to
    # names.
    uri_lookup = {}
    typ_lookup = {}
    tv_lookup = {}
    fn_lookup = {}
    if extension_uris or extensions:
        output.append('\n// Type/function extensions\n')
        for extension_uri in extension_uris:
            with MessageUnpacker('extensionUriAnchor', extension_uris) as u:
                anchor = u.pop('extensionUriAnchor', int, 0)
                uri = u.pop('uri', str)
            if not isinstance(anchor, int) or anchor < 0:
                raise TypeError(f'illegal URI anchor value {anchor}')
            ref = uniquify(make_ident('uri', uri.rsplit('/', maxsplit=1)[-1].split('.', maxsplit=1)[0]))
            uri = make_string(uri)
            output.append(f'using {ref} = {uri} = {anchor};\n')
            uri_lookup[anchor] = ref
        if extension_uris:
            output.append('\n')
        for extension in extensions:
            with OneOfMessageUnpacker('extension', extension) as u:
                if u.handle('extensionFunction'):
                    with MessageUnpacker('function extension', u.val) as v:
                        uri_ref = v.pop('extensionUriReference', int, 0)
                        anchor = v.pop('functionAnchor', int, 0)
                        name = v.pop('name', str)
                        decl = 'function'
                        prefix = 'fn'
                        lookup = fn_lookup
                elif u.handle('extensionType'):
                    with MessageUnpacker('type extension', u.val) as v:
                        uri_ref = v.pop('extensionUriReference', int, 0)
                        anchor = v.pop('typeAnchor', int, 0)
                        name = v.pop('name', str)
                        decl = 'type'
                        prefix = 'typ'
                        lookup = typ_lookup
                elif u.handle('extensionTypeVariation'):
                    with MessageUnpacker('type extension', u.val) as v:
                        uri_ref = v.pop('extensionUriReference', int, 0)
                        anchor = v.pop('typeVariationAnchor', int, 0)
                        name = v.pop('name', str)
                        decl = 'type_variation'
                        prefix = 'tv'
                        lookup = tv_lookup
            if not isinstance(anchor, int) or anchor < 0:
                raise TypeError(f'illegal {decl} anchor value {anchor}')
            ref_name = {
                '+': 'add',
                '-': 'sub',
                '*': 'mult',
                '/': 'div',
            }.get(name, name)
            ref = uniquify(make_ident(prefix, ref_name))
            if uri_ref == 0:
                uri_ref = ''
            else:
                uri_ref = uri_lookup.get(uri_ref, uri_ref)
                uri_ref = f'{uri_ref}::'
            if not is_ident(name):
                name = make_string(name)
            output.append(f'{decl} {ref} = {uri_ref}{name} = {anchor};\n')
            lookup[anchor] = ref

    # Emit protobuf-level extension declarations.
    if toplevel_enhancement or toplevel_optimization or expected_type_urls:
        output.append('\n// Protobuf extensions\n')
        for expected_type_url in expected_type_urls:
            url = make_string(expected_type_url)
            output.append(f'proto_extension {url};\n')
        if toplevel_enhancement:
            data = json.dumps(toplevel_enhancement, indent=2)
            output.append(f'enhancement {data};\n')
        if toplevel_optimization:
            data = json.dumps(toplevel_optimization, indent=2)
            output.append(f'optimization {data};\n')

    # Emit relations.
    def emit_raw_json(ref, data):
        def dfs_helper(node, indent=''):
            if isinstance(node, dict):
                retval = [f'{{']
                first = True
                for key, val in node.items():
                    if first:
                        first = False
                    else:
                        retval.append(',')
                    key_str = make_string(key)
                    retval.append(f'\n{indent}  {key_str}: ')

                    # TODO: this simple key matching is NOT foolproof! We're
                    # dealing with the fact that protobuf JSON serialization
                    # provides no context about what kind of message we're
                    # parsing. What we WANT to match here is fields of
                    # particular message types, but we're lacking that type
                    # information right now. Instead we'll just have to make
                    # do with the field name and rudimentary checking of the
                    # JSON field type.
                    # TODO: also this code is super ugly.
                    behavior = {
                        'functionReference': ('extension_ref', fn_lookup),
                        'comparisonFunctionReference': ('extension_ref', fn_lookup),
                        'userDefinedTypeReference': ('extension_ref', typ_lookup),
                        'typeVariationReference': ('extension_ref', tv_lookup),
                        'input': ('subtree', next(iter(val)) if isinstance(val, dict) and val else 'unknown'),
                    }.get(key, ('recurse',))

                    if behavior[0] == 'extension_ref' and isinstance(val, int):
                        lookup_table = behavior[1]
                        retval.append(lookup_table.get(val, str(val)))
                        continue
                    if behavior[0] == 'subtree' and isinstance(val, dict):
                        subtree = dfs_helper(val)
                        subref = uniquify(make_ident(ref, behavior[1]))
                        output.append(f'raw {subref} = {subtree};\n\n')
                        retval.append(subref)
                        continue
                    retval.append(dfs_helper(val, f'{indent}  '))

                retval.append(f'\n{indent}}}')
                return ''.join(retval)
            elif isinstance(node, list):
                retval = [f'[']
                first = True
                for val in node:
                    if first:
                        first = False
                    else:
                        retval.append(f',')
                    retval.append(f'\n{indent}  ')
                    retval.append(dfs_helper(val, f'{indent}  '))
                retval.append(f'\n{indent}]')
                return ''.join(retval)

            # Can just handle leaf types with json lib
            return json.dumps(node)

        root = dfs_helper(data)
        output.append(f'raw {ref} = {root};\n\n')

    for index, relation in enumerate(relations):
        output.append(f'\n// Relation {index}\n')
        with OneOfMessageUnpacker('relation root', relation) as u:
            if u.handle('root'):
                with MessageUnpacker('relation root', u.val) as v:
                    rel = v.pop('input', int, 0)
                    names = v.pop('names', list, 0)
                    for name in names:
                        if not isinstance(name, str):
                            actual = type(name)
                            raise TypeError(f'relation root relation names must be strings, found {actual}')
                    names = ', '.join(map(make_string, names))
                    names = f'({names})'
                ref = emit_rels(rel)
            elif u.handle('rel'):
                rel = u.val
                names = ''

            ref = uniquify(make_ident('rel', str(index)))
            emit_raw_json(ref, rel)
            output.append(f'execute {ref}{names};\n')


    return ''.join(output)




print(disas("""
{
 "extensionUris": [],
 "extensions": [
  {
   "extensionFunction": {
    "extensionUriReference": 0,
    "functionAnchor": 0,
    "name": "lessthanequal"
   }
  },
  {
   "extensionFunction": {
    "extensionUriReference": 0,
    "functionAnchor": 1,
    "name": "is_not_null"
   }
  },
  {
   "extensionFunction": {
    "extensionUriReference": 0,
    "functionAnchor": 2,
    "name": "and"
   }
  },
  {
   "extensionFunction": {
    "extensionUriReference": 0,
    "functionAnchor": 3,
    "name": "*"
   }
  },
  {
   "extensionFunction": {
    "extensionUriReference": 0,
    "functionAnchor": 4,
    "name": "-"
   }
  },
  {
   "extensionFunction": {
    "extensionUriReference": 0,
    "functionAnchor": 5,
    "name": "sum"
   }
  },
  {
   "extensionFunction": {
    "extensionUriReference": 0,
    "functionAnchor": 6,
    "name": "+"
   }
  },
  {
   "extensionFunction": {
    "extensionUriReference": 0,
    "functionAnchor": 7,
    "name": "avg"
   }
  },
  {
   "extensionFunction": {
    "extensionUriReference": 0,
    "functionAnchor": 8,
    "name": "count_star"
   }
  }
 ],
 "relations": [
  {
   "rel": {
    "sort": {
     "input": {
      "project": {
       "input": {
        "aggregate": {
         "input": {
          "project": {
           "input": {
            "read": {
             "common": {
              "direct": {}
             },
             "filter": {
              "scalarFunction": {
               "functionReference": 2,
               "args": [
                {
                 "scalarFunction": {
                  "functionReference": 0,
                  "args": [
                   {
                    "selection": {
                     "directReference": {
                      "structField": {
                       "field": 10
                      }
                     }
                    }
                   },
                   {
                    "literal": {
                     "nullable": false,
                     "string": "1998-09-02"
                    }
                   }
                  ]
                 }
                },
                {
                 "scalarFunction": {
                  "functionReference": 1,
                  "args": [
                   {
                    "selection": {
                     "directReference": {
                      "structField": {
                       "field": 10
                      }
                     }
                    }
                   }
                  ]
                 }
                }
               ]
              }
             },
             "projection": {
              "select": {
               "structItems": [
                {
                 "field": 10
                },
                {
                 "field": 8
                },
                {
                 "field": 9
                },
                {
                 "field": 4
                },
                {
                 "field": 5
                },
                {
                 "field": 6
                },
                {
                 "field": 7
                }
               ]
              },
              "maintainSingularStruct": false
             },
             "namedTable": {
              "names": [
               "lineitem"
              ]
             }
            }
           },
           "expressions": [
            {
             "selection": {
              "directReference": {
               "structField": {
                "field": 1
               }
              }
             }
            },
            {
             "selection": {
              "directReference": {
               "structField": {
                "field": 2
               }
              }
             }
            },
            {
             "selection": {
              "directReference": {
               "structField": {
                "field": 3
               }
              }
             }
            },
            {
             "selection": {
              "directReference": {
               "structField": {
                "field": 4
               }
              }
             }
            },
            {
             "scalarFunction": {
              "functionReference": 3,
              "args": [
               {
                "selection": {
                 "directReference": {
                  "structField": {
                   "field": 4
                  }
                 }
                }
               },
               {
                "scalarFunction": {
                 "functionReference": 4,
                 "args": [
                  {
                   "literal": {
                    "decimal": {
                     "value": "MTAw",
                     "precision": 16,
                     "scale": 2
                    },
                    "nullable": false
                   }
                  },
                  {
                   "selection": {
                    "directReference": {
                     "structField": {
                      "field": 5
                     }
                    }
                   }
                  }
                 ]
                }
               }
              ]
             }
            },
            {
             "selection": {
              "directReference": {
               "structField": {
                "field": 6
               }
              }
             }
            },
            {
             "selection": {
              "directReference": {
               "structField": {
                "field": 5
               }
              }
             }
            }
           ]
          }
         },
         "groupings": [
          {
           "groupingExpressions": [
            {
             "selection": {
              "directReference": {
               "structField": {
                "field": 0
               }
              }
             }
            },
            {
             "selection": {
              "directReference": {
               "structField": {
                "field": 1
               }
              }
             }
            }
           ]
          }
         ],
         "measures": [
          {
           "measure": {
            "functionReference": 5,
            "args": [
             {
              "selection": {
               "directReference": {
                "structField": {
                 "field": 2
                }
               }
              }
             }
            ],
            "sorts": [],
            "phase": "AGGREGATION_PHASE_UNSPECIFIED"
           }
          },
          {
           "measure": {
            "functionReference": 5,
            "args": [
             {
              "selection": {
               "directReference": {
                "structField": {
                 "field": 3
                }
               }
              }
             }
            ],
            "sorts": [],
            "phase": "AGGREGATION_PHASE_UNSPECIFIED"
           }
          },
          {
           "measure": {
            "functionReference": 5,
            "args": [
             {
              "selection": {
               "directReference": {
                "structField": {
                 "field": 4
                }
               }
              }
             }
            ],
            "sorts": [],
            "phase": "AGGREGATION_PHASE_UNSPECIFIED"
           }
          },
          {
           "measure": {
            "functionReference": 5,
            "args": [
             {
              "scalarFunction": {
               "functionReference": 3,
               "args": [
                {
                 "selection": {
                  "directReference": {
                   "structField": {
                    "field": 4
                   }
                  }
                 }
                },
                {
                 "scalarFunction": {
                  "functionReference": 6,
                  "args": [
                   {
                    "literal": {
                     "decimal": {
                      "value": "MTAw",
                      "precision": 16,
                      "scale": 2
                     },
                     "nullable": false
                    }
                   },
                   {
                    "selection": {
                     "directReference": {
                      "structField": {
                       "field": 5
                      }
                     }
                    }
                   }
                  ]
                 }
                }
               ]
              }
             }
            ],
            "sorts": [],
            "phase": "AGGREGATION_PHASE_UNSPECIFIED"
           }
          },
          {
           "measure": {
            "functionReference": 7,
            "args": [
             {
              "selection": {
               "directReference": {
                "structField": {
                 "field": 2
                }
               }
              }
             }
            ],
            "sorts": [],
            "phase": "AGGREGATION_PHASE_UNSPECIFIED"
           }
          },
          {
           "measure": {
            "functionReference": 7,
            "args": [
             {
              "selection": {
               "directReference": {
                "structField": {
                 "field": 3
                }
               }
              }
             }
            ],
            "sorts": [],
            "phase": "AGGREGATION_PHASE_UNSPECIFIED"
           }
          },
          {
           "measure": {
            "functionReference": 7,
            "args": [
             {
              "selection": {
               "directReference": {
                "structField": {
                 "field": 6
                }
               }
              }
             }
            ],
            "sorts": [],
            "phase": "AGGREGATION_PHASE_UNSPECIFIED"
           }
          },
          {
           "measure": {
            "functionReference": 8,
            "args": [],
            "sorts": [],
            "phase": "AGGREGATION_PHASE_UNSPECIFIED"
           }
          }
         ]
        }
       },
       "expressions": [
        {
         "selection": {
          "directReference": {
           "structField": {
            "field": 0
           }
          }
         }
        },
        {
         "selection": {
          "directReference": {
           "structField": {
            "field": 1
           }
          }
         }
        },
        {
         "selection": {
          "directReference": {
           "structField": {
            "field": 2
           }
          }
         }
        },
        {
         "selection": {
          "directReference": {
           "structField": {
            "field": 3
           }
          }
         }
        },
        {
         "selection": {
          "directReference": {
           "structField": {
            "field": 4
           }
          }
         }
        },
        {
         "selection": {
          "directReference": {
           "structField": {
            "field": 5
           }
          }
         }
        },
        {
         "selection": {
          "directReference": {
           "structField": {
            "field": 6
           }
          }
         }
        },
        {
         "selection": {
          "directReference": {
           "structField": {
            "field": 7
           }
          }
         }
        },
        {
         "selection": {
          "directReference": {
           "structField": {
            "field": 8
           }
          }
         }
        },
        {
         "selection": {
          "directReference": {
           "structField": {
            "field": 9
           }
          }
         }
        }
       ]
      }
     },
     "sorts": [
      {
       "expr": {
        "selection": {
         "directReference": {
          "structField": {
           "field": 0
          }
         }
        }
       },
       "direction": "SORT_DIRECTION_ASC_NULLS_FIRST"
      },
      {
       "expr": {
        "selection": {
         "directReference": {
          "structField": {
           "field": 1
          }
         }
        }
       },
       "direction": "SORT_DIRECTION_ASC_NULLS_FIRST"
      }
     ]
    }
   }
  }
 ],
 "expectedTypeUrls": []
}
"""))
