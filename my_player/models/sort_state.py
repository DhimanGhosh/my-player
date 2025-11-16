from dataclasses import dataclass


@dataclass
class SortState:
    column_key: str
    ascending: bool

    def toggle_if_same(self, column_key: str):
        if self.column_key == column_key:
            self.ascending = not self.ascending
        else:
            self.column_key = column_key
            self.ascending = True
