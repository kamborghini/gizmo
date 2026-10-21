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
the wrong kind is a 400 naming it: "The title sent must be text."

On the floor: it imports nothing from the app.
"""
import math
import re
from typing import Annotated, Any, Optional, Union

from pydantic import BaseModel, ConfigDict, PlainValidator, ValidationError
from pydantic_core import PydanticCustomError


def _kind(words: str, fits):
    """A field kind: the values it takes, and its plain words for a refusal."""
    def check(v):
        if v is None or fits(v):
            return v
        raise PydanticCustomError("body_kind", words)
    return Annotated[Any, PlainValidator(check)]


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _number_text(v) -> bool:
    if not isinstance(v, str):
        return False
    if v == "":
        return True          # an empty box: the route reads it as nothing
    try:
        return math.isfinite(float(v))
    except ValueError:
        return False


_WHOLE_TEXT = re.compile(r"\s*[+-]?\d+\s*")

# The kinds. Each takes what the page sends today: a number typed in a box
# arrives as text, and an id may be text or a number (Shopify's are numbers).
Text = _kind("text", lambda v: isinstance(v, str))
Id = _kind("text or a number", lambda v: isinstance(v, str) or (_number(v) and float(v).is_integer()))
Whole = _kind("a whole number", lambda v: _number(v) or v == "" or (isinstance(v, str) and bool(_WHOLE_TEXT.fullmatch(v))))
Number = _kind("a number", lambda v: _number(v) or _number_text(v))
Flag = _kind("yes or no", lambda v: isinstance(v, bool) or (isinstance(v, int) and v in (0, 1)))
Items = _kind("a list", lambda v: isinstance(v, list))
Fields = _kind("a set of fields", lambda v: isinstance(v, dict))


class Body(BaseModel):
    """A request body: the fields named below are checked, the rest pass."""
    model_config = ConfigDict(extra="allow")


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
