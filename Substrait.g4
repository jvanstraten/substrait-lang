grammar Substrait;

// File structure
//  - should hopefully resemble javascript enough that a javascript syntax
//    highlighter can make sense of it (though this is definitely not a strict
//    subset of javascript due to the additional keywords)
//  - think of this as a bunch of syntactic sugar on top of the JSON
//    representation of a Substrait plan message
//  - the toplevel object of the plan message can only be defined using special
//    syntax, primarily such that someone reading the file doesn't have to
//    keep track of anchors and references. Everything inside a relation can be
//    specified with the raw_json statement if needed, but ideally additional
//    statements will be added later to make relations and expressions easier
//    to write than said raw JSON
//  - the parser state consists of:
//     - $json: ident -> json, i.e. a map from identifiers to JSON excerpts
//       (basically, think of them as constant variable declarations)
//     - $uri_anchor: int, starting at 0, to track how many URI anchors have
//       been added and to uniquify them
//     - $type_anchor: int, as above for user-defined type anchors
//     - $type_var_anchor: int, as above for user-defined type variation anchors
//     - $function_anchor: int, as above for function anchors
//     - the toplevel JSON structure, which starts off as
//       {
//         "extension_uris": [],
//         "extensions": [],
//         "relations": [],
//         "advanced_extensions": {},
//         "expected_type_urls": [],
//       }
//    as parsing proceeds, this state is updated in a single pass (this means
//    that you can't refer to some JSON excerpt that you haven't defined yet,
//    and that it's perfectly legal to redefine which JSON excerpt an
//    identifier refers to). When done, simply emit the toplevel JSON structure
//  - in the "disassembling" direction:
//     - define all URI anchors using extension_decl statements, using some
//       uniquified variable name based on the YAML basename, prefixed with
//       "uri_"
//     - define all function/type/variation anchors using the appropriate
//       statements, using some uniquified variable name based on the
//       function/type/variation name, prefixed with "fn_"/"typ_"/"tv_"
//     - if expected_type_uris is non-empty, declare as needed using
//       proto_extension_decl statements
//     - if advanced_extensions is non-empty, declare as needed using
//       enhancement_decl and/or optimization_decl
//     - for each toplevel relation:
//        - DFS through the tree:
//           - whenever a relation is encountered, emit a new raw_json
//             statement for it, using some uniquified name (probably just
//             "rel_#" where # is a counter
//           - whenever a function/type/variation reference is encountered,
//             replace the number with a reference to the anchors we defined
//             earlier
//        - emit an execute_statement for the toplevel relation
substrait
    : (statement ';')* EOF
    ;
statement
    : extension_decl
    | function_decl
    | type_decl
    | type_var_decl
    | proto_extension_decl
    | enhancement_decl
    | optimization_decl
    | execute_statement
    | raw_json
    ;


// Extension URI declaration
//  - if no anchor exists for the referred URI yet, reserves a URI
//    anchor/reference for the given URI in "extensionUris" by appending the
//    following to it:
//    {
//      "extensionUriAnchor": $++uri_anchor,
//      "uri": $4
//    }
//  - sets $json[$2] to $uri_anchor
//  - if $6 is specified, set $uri_anchor to that value minus 1 prior to the
//    above (such that the anchor will match the specified value after the
//    pre-increment), and force the append operation to "extension_uris"
extension_decl
    : 'using' ident '=' string ('=' unsigned_int)?
    ;


// Explicit function declaration
//  - if no function anchor exists for the referred function yet, reserves a
//    function anchor/reference for the given function in "extensions" by
//    appending the following to it:
//    {
//      "extensionFunction": {
//        "extensionUriReference": $4,
//        "functionAnchor": $++fn_anchor,
//        "name": $6
//      }
//    }
//  - sets $json[$2] to $function_anchor
//  - if $9 is specified, set $fn_anchor to that value minus 1 prior to the
//    above (such that the anchor will match the specified value after the
//    pre-increment), and force the append operation to "extensions"
function_decl
    : 'function' ident '=' (uri_ref '::')? (ident | string) ('=' unsigned_int)?
    ;


// Explicit extension type declaration
//  - if no type anchor exists for the referred type yet, reserves a
//    type anchor/reference for the given type in "extensions" by
//    appending the following to it:
//    {
//      "extensionType": {
//        "extensionUriReference": $4,
//        "typeAnchor": $++type_anchor,
//        "name": $6
//      }
//    }
//  - sets $json[$2] to $type_anchor
//  - if $9 is specified, set $type_anchor to that value minus 1 prior to the
//    above (such that the anchor will match the specified value after the
//    pre-increment), and force the append operation to "extensions"
type_decl
    : 'type' ident '=' (uri_ref '::')? (ident | string) ('=' unsigned_int)?
    ;


// Explicit type variation declaration
//  - if no type variation anchor exists for the referred type variation yet,
//    reserves a type variation anchor/reference for the given type in
//    "extensions" by appending the following to it:
//    {
//      "extension_type_variation": {
//        "extension_uri_reference": $4,
//        "type_variation_anchor": $++type_var_anchor,
//        "name": $6
//      }
//    }
//  - sets $json[$2] to $type_var_anchor
//  - if $9 is specified, set $type_var_anchor to that value minus 1 prior to the
//    above (such that the anchor will match the specified value after the
//    pre-increment), and force the append operation to "extensions"
type_var_decl
    : 'type_variation' ident '=' (uri_ref '::')? (ident | string) ('=' unsigned_int)?
    ;


// Reference to a URI
//  - if identifier, yields $json[$1]
//  - if integer, yields $1
uri_ref
    : ident
    | unsigned_int
    ;


// Protobuf extension declaration
//  - appends $2 to "expectedTypeUrls"
proto_extension_decl
    : 'proto_extension' string
    ;


// Advanced extension enhancement declaration
//  - sets "advancedExtensions"."enhancement" to $2
enhancement_decl
    : 'enhancement' json_value
    ;


// Advanced extension optimization declaration
//  - sets "advancedExtensions"."optimization" to $2
optimization_decl
    : 'optimization' json_value
    ;


// Toplevel relation declaration
//  - if $2 (rel_root_names) is specified, appends the following to
//    "relations":
//    {
//      "root": {
//        "input": $json[$2],
//        "names": $json_list[$3]
//      }
//    }
//  - if $3 (rel_root_names) is not specified, appends the following to
//    "relations":
//    {
//      "rel": $json[$2]
//    }
execute_statement
    : 'execute' ident rel_root_names?
    ;
rel_root_names
    : '(' string (',' string) ','? ')'
    | '(' ','? ')'
    ;


// Raw JSON input
//  - sets $json[$2] to $4
raw_json
    : 'raw' ident '=' json_value
    ;


// JSON values
//  - this is just normal JSON syntax, with the exception of ident: this rule
//    will match 'true', 'false', and 'null' as defined by JSON, but will
//    match any other identifier as well. If not one of the JSON-defined
//    identifiers, replace with $json[$1], i.e. dereference the JSON excerpt
//    map.
json_value
    : ident
    | string
    | json_number
    | json_obj
    | json_array
    ;


// JSON objects
//  - exactly as defined by JSON, except that a comma at the end is allowed
json_obj
    : '{' json_key_value (',' json_key_value)* ','? '}'
    | '{' ','? '}'
    ;
json_key_value
    : string ':' json_value
    ;


// JSON arrays
//  - exactly as defined by JSON, except that a comma at the end is allowed
json_array
    : '[' json_value (',' json_value)* ','? ']'
    | '[' ','? ']'
    ;


// JSON numbers
//  - exactly as defined by JSON
//  - note: while this could just be a single token, this would make expression
//    parsing later more difficult
json_number
    : signed_int
    | signed_real
    ;


// Integers
signed_int
    : unsigned_int
    | '-' unsigned_int
    ;
unsigned_int
    : UNSIGNED_INT
    ;
UNSIGNED_INT
    : '0' | [1-9] [0-9]*
    ;


// Real numbers
signed_real
    : unsigned_real
    | '-' unsigned_real
    ;
unsigned_real
    : UNSIGNED_INT REAL_FRACTION REAL_EXP?
    | UNSIGNED_INT REAL_EXP
    ;
REAL_FRACTION
    : ('.' [0-9] +)
    ;
REAL_EXP
    : [Ee] [+\-]? UNSIGNED_INT
    ;


// Identifiers
//  - the usual definition
ident
    : IDENT
    ;
IDENT
    : [a-zA-Z_][a-zA-Z0-9_]*
    ;


// String literals
//  - exactly as defined by JSON
string
    : STRING
    ;
STRING
    : '"' (STRING_ESCAPE | CHARACTER)* '"'
    ;
fragment STRING_ESCAPE
    : '\\' (["\\/bfnrt] | STRING_UNICODE_ESCAPE)
    ;
fragment STRING_UNICODE_ESCAPE
    : 'u' HEX_DIGIT HEX_DIGIT HEX_DIGIT HEX_DIGIT
    ;
fragment HEX_DIGIT
    : [0-9a-fA-F]
    ;
fragment CHARACTER
    : ~ ["\\\u0000-\u001F]
    ;


// Whitespace/comment handling
//  - as in javascript, C++, etc.
WHITESPACE
    : [ \t\n\r] + -> skip
    ;
BLOCK_COMMENT
    : '/*' .*? '*/' -> skip
    ;
LINE_COMMENT
    : '//' .*? '\n' -> skip
    ;
