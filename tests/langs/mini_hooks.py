from blockwright import model as M


def if_as_decision(builder, node, rule):
    cond = builder.cond_text(node.child_by_field_name("condition"))
    fail = M.Simple(M.TERMINATOR, builder.L("exception_bare"), terminal=True)
    return [M.If(cond, M.Seq([]), M.Seq([fail]))]
