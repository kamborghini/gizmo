"""Request bodies checked at the door (stage 5 of the 14 October audit).

A route that changes something reads fields from the body the page sends. Each
route checked its own, and a field of the wrong kind (an object where a name
belongs) either broke the route with a server error or was saved as nonsense.
A model here names the fields a route reads and the kind each must be:

    class MemoryBody(bodies.Body):
        id: bodies.Id = None
        text: bodies.Text = None

    err, body, who = await gate._guard(request, model=MemoryBody)

or one model per `op`, as {"add": AddBody, "delete": DeleteBody}, where an op
the dict does not name reaches the route as before. Only the named fields are
checked; every other field passes, a field left out or sent as null is the
route's to decide, and the route reads the body exactly as it came. A field of
the wrong kind is a 400 naming it: "The title sent must be text." A field
sent under a name Python keeps for itself is declared with `named("from")`.

On the floor: it imports nothing from the app.
"""
import math
import re
import sys
from typing import Annotated, Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, PlainValidator, ValidationError
from pydantic_core import PydanticCustomError


def _kind(words: str, fits):
    """A field kind: the values it takes, and its plain words for a refusal."""
    def check(v):
        if v is None or fits(v):
            return v
        raise PydanticCustomError("body_kind", words)
    return Annotated[Any, PlainValidator(check)]


def _number(v) -> bool:
    """A JSON number a route can do sums with. An integer is compared, never
    converted: JSON may carry one with hundreds of digits, which float() and
    math.isfinite() raise on, and a check must refuse, not fail."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return abs(v) <= sys.float_info.max
    return isinstance(v, float) and math.isfinite(v)


def _number_text(v) -> bool:
    if not isinstance(v, str):
        return False
    if v == "":
        return True          # an empty box: the route reads it as nothing
    try:
        return math.isfinite(float(v))
    except ValueError:
        return False


_WHOLE_TEXT = re.compile(r"\s*[+-]?\d{1,30}\s*")      # int() refuses text past 4,300 digits
# The largest whole number a browser sends exactly: JSON.stringify of a bigger
# one is already rounded, and a route that does sums or dates with one (a
# number of months, a number of days) overflows on the way.
_SAFE_WHOLE = 2 ** 53


def _whole(v) -> bool:
    if v == "":
        return True          # an empty box: the route reads it as nothing
    if isinstance(v, str):
        return bool(_WHOLE_TEXT.fullmatch(v)) and abs(int(v)) <= _SAFE_WHOLE
    return _number(v) and abs(v) <= _SAFE_WHOLE

# The kinds. Each takes what the page sends today: a number typed in a box
# arrives as text, and an id may be text or a number (Shopify's are numbers).
Text = _kind("text", lambda v: isinstance(v, str))
Id = _kind("text or a number", lambda v: isinstance(v, str) or (_number(v) and float(v).is_integer()))
Whole = _kind("a whole number", _whole)
Number = _kind("a number", lambda v: _number(v) or _number_text(v))
Flag = _kind("yes or no", lambda v: isinstance(v, bool) or (isinstance(v, int) and v in (0, 1)))
Items = _kind("a list", lambda v: isinstance(v, list))
# A list whose every item is a set of fields: a chat's messages, say.
Records = _kind("a list of sets of fields", lambda v: isinstance(v, list) and all(isinstance(x, dict) for x in v))
Fields = _kind("a set of fields", lambda v: isinstance(v, dict))


class Body(BaseModel):
    """A request body: the fields named below are checked, the rest pass."""
    model_config = ConfigDict(extra="allow")


def named(sent: str):
    """A field sent under a name Python keeps for itself ("from"):
    `frm: bodies.Text = bodies.named("from")`."""
    return Field(None, alias=sent)


def sent_names(model: type) -> list:
    """The field names a model checks, as a body sends them."""
    return [info.alias or name for name, info in model.model_fields.items()]


Model = Union[type, dict]


def model_for(model: Model, body: dict) -> Optional[type]:
    """The model that checks this body: the one given, or its op's."""
    if not isinstance(model, dict):
        return model
    op = body.get("op")
    return model.get(op) if isinstance(op, str) else None


def refusal(model: Model, body: dict) -> Optional[str]:
    """None when every field the model names is of its kind; otherwise the
    plain words for the first that is not."""
    m = model_for(model, body)
    if m is None:
        return None
    try:
        m.model_validate(body)
    except ValidationError as e:
        first = e.errors()[0]
        name = str(first["loc"][0]).replace("_", " ")
        return "The %s sent must be %s." % (name, first["msg"])
    return None
