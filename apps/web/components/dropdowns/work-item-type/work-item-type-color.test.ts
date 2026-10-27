import assert from "node:assert/strict";
import { test } from "node:test";
import { WORK_TYPE_COLORS, workTypeColors } from "./work-item-type-color";

test("badge text stays readable with both light and dark work type colors", () => {
  assert.deepEqual(workTypeColors("#FFFFFF"), { backgroundColor: "#FFFFFF", color: "#000000" });
  assert.deepEqual(workTypeColors("#000000"), { backgroundColor: "#000000", color: "#FFFFFF" });
  for (const color of WORK_TYPE_COLORS) {
    assert.equal(workTypeColors(color).backgroundColor, color);
  }
});

test("missing or invalid colors use a neutral fallback rather than changing type identity", () => {
  for (const value of [null, undefined, "red", "#fff", "url(invalid)"]) {
    assert.equal(workTypeColors(value).backgroundColor, "#64748B");
  }
});
