# Reading the radar

The radar renders the curated board as a **polar plot**: a circle divided into rings
and sectors, with each item drawn as a dot. Once you know how the two coordinates
from the [radar model](./radar-model.md) map onto the picture, the whole board reads
at a glance.

## Rings are concentric bands

The circle is split into concentric bands, one per ring, ordered by readiness from
the center outward:

- The **innermost** band is `Use` — the things ready to act on now.
- Moving outward: `Prototype`, then `Evaluate`, then `Watch` at the rim.

So *distance from the center is inverse readiness*: the closer a dot is to the
middle, the more the radar is saying "this is ready." The `Ignore` ring is not drawn
on the public board at all — public viewers never see the slush pile — so a
published radar shows four bands, not five.

## Quadrants are sectors

The circle is cut into four sectors, one per [quadrant](./radar-model.md):
perception, scene, models, and tooling. A dot's sector tells you *what kind of vision
problem* the item addresses. Within each quadrant sector the space is further
subdivided by track, so items cluster near the track they belong to. A dot's angle
therefore encodes its topic, and its radius encodes its ring — position alone tells
you both coordinates.

Dot placement is deterministic: the same item lands in the same spot across renders,
so the board is stable to read from day to day rather than reshuffling on every
refresh.

## Movement shown as a pulse

A radar is only interesting because it changes, so change is made visible. An item
that is **new** to the board, or that has just **moved in** to a higher ring, is
drawn with an animated pulse — a halo that expands out from the dot — so recent
activity catches the eye without any hunting. Items that have **moved out** to a
lower ring are labeled as such when inspected. The three movement states are simply:

| Movement | Meaning |
|----------|---------|
| new | first appearance on the board |
| moved in | promoted toward the center |
| moved out | demoted toward the rim |

The pulse is deliberately reserved for arrivals and promotions — the events a reader
most wants to notice.

## The same data, re-projected

The polar plot is one view of the curated board, not the only one. The other views
re-project the *same* underlying decisions:

- **Tracks** groups items by track rather than by angle, giving a per-track reading
  list — useful when you care about one area of the field rather than the whole
  board.
- **Timeline** lays the board out over time — recent weeks of activity, with a strip
  of recent movers — so you can see momentum rather than a single snapshot.

Because every view is a re-projection of the same curated decisions, they never
disagree; they just emphasize a different axis — topic, or time, or readiness. Where
that curated data comes from, and how it becomes a static site, is the subject of the
[final chapter](./how-this-site-is-built.md).
