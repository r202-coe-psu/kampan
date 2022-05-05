from wtforms import widgets
from wtforms.fields import Field


class TagListField(Field):
    widget = widgets.TextInput()

    def __init__(self, label="", validators=None, remove_duplicates=True, **kwargs):
        super().__init__(label, validators, **kwargs)
        self.remove_duplicates = remove_duplicates

    def process_formdata(self, valuelist):
        self.data = []
        if valuelist:
            for l in valuelist[0].splitlines():
                for tag in l.split(","):
                    tag = tag.strip()
                    if not tag:
                        continue

                    if tag not in self.data:
                        self.data.append(tag)

    def _value(self):
        if self.data:
            return ", ".join(self.data)
        else:
            return ""

    @classmethod
    def _remove_duplicates(cls, seq):
        """Remove duplicates in a case insensitive, but case preserving manner"""
        d = {}
        for item in seq:
            if item not in d:
                d[item] = True
                yield item


class TextListField(TagListField):
    widget = widgets.TextArea()
