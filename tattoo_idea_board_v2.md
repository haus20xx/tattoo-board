# Tattoo Vision Board (v2)

Organize the high-level approach to some tattoo ideas, starting with visual
categorization.

## Format

Each category contains a YAML list of items. Fields:

- `url` (required): link to the inspiration item
- `note` (optional): short description / keywords
- `kind` (required): `tattoo` | `art` | `lookbook`
- `starred` (optional, bool): `true` for particularly noteworthy items
- `owned` (optional, bool): `true` if already purchased / printed / inked
- `todo` (optional): freeform note flagging something to revisit

## Outer Wilds

```yaml
- url: https://www.instagram.com/p/DRGbX3KkuoK/
  note: eye + coordinates
  kind: tattoo
  starred: true
- url: https://www.instagram.com/p/DJpMRWBM52A/
  note: above + solar system
  kind: tattoo
- url: https://www.instagram.com/p/DRGbX3KkuoK/
  note: adjusted art style, skull of strangers
  kind: tattoo
  todo: duplicate URL with eye + coordinates entry above; verify intended link
- url: https://www.instagram.com/p/DIU1xXcATlK/
  note: clean eye
  kind: tattoo
- url: https://www.instagram.com/p/DWZXXklDtC9/
  note: nomai mask
  kind: tattoo
- url: https://static.wikia.nocookie.net/outerwilds_gamepedia/images/0/08/The_Stranger_built.png/revision/latest?cb=20211003103629
  note: the stranger
  kind: art
- url: https://ih1.redbubble.net/image.2982186309.0146/flat,750x,075,f-pad,750x1000,f8f8f8.jpg
  note: the stranger symbol; not standalone, used with universe map
  kind: art
- url: https://i.redd.it/n8xume0xh5q81.jpg
  note: my tattoo but better
  kind: tattoo
- url: https://pbs.twimg.com/media/FS1Ia_MWAAApGXr?format=jpg&name=large
  kind: art
- url: https://rlv.zcache.com/the_outer_wilds_solar_system_poster-rfddc025bb6444f77aa38398fa27d6b8e_a21qmd_8byvr_644.webp
  note: icon solar system
  kind: art
- url: https://i.pinimg.com/170x/be/ed/d0/beedd0d6fae4e2d36ed5824c4fc71e13.jpg
  note: toy planet
  kind: art
- url: https://www.reddit.com/r/outerwilds/comments/10662ni/i_redrew_the_mural_from_the_place_you_can_go_with/
  note: cool concept sketch
  kind: art
- url: https://static.wikia.nocookie.net/outerwilds_gamepedia/images/8/8c/Statue_Workshop_Statue_mask_Nomai_interaction.png/revision/latest?cb=20201021150642
  note: in-game nomai sketch
  kind: art
- url: https://i.pinimg.com/236x/ae/37/3d/ae373db0f505a33e09957c7bcb72049e.jpg
  note: cool framing, combined with stylistic tall priest style?
  kind: art
- url: https://payload.cargocollective.com/1/8/263533/13488403/Sunstation-B_1200.jpg
  note: sun station
  kind: art
- url: https://payload.cargocollective.com/1/8/263533/13488403/ian-jacobson-monolith_1200.jpg
  note: cool monolith
  kind: art
- url: https://www.ianjacobson.com/Outer-Wilds
  note: official concept art (index)
  kind: art
- url: https://payload.cargocollective.com/1/8/263533/13488403/ian-jacobson-white-hole-station_1200.jpg
  note: cool sun station
  kind: art
- url: https://payload.cargocollective.com/1/8/263533/13488403/Nomai-Escape-Pod-B_1200.jpg
  note: escape pod
  kind: art
- url: https://payload.cargocollective.com/1/8/263533/14324465/19-C_1200.jpg
  note: the cell
  kind: art
- url: https://www.instagram.com/p/DJoDYu2IDkk/
  note: Doorlike
  kind: art
```

## Instrument

```yaml
- url: https://www.instagram.com/p/DDejJ9qiOZI/
  note: woodcut
  kind: tattoo
- url: https://shop.micahulrich.com/product/the-musician-8-5-x11-watercolor-print
  note: micah ulrich
  kind: art
  owned: true
```

## Nature / Tree

```yaml
- url: https://www.instagram.com/p/DD4eijqvfaH/
  note: bonsai style
  kind: tattoo
- url: https://www.instagram.com/p/C2sShzIqViE/
  note: sun, moon, cloud
  kind: tattoo
- url: https://www.instagram.com/p/CzME-NFCx7w/
  note: striking tree, lightning
  kind: tattoo
- url: https://www.instagram.com/p/DX61pK1kXuH/
  note: chalice and nature
  kind: tattoo
```

## Surreal

```yaml
- url: https://www.instagram.com/p/DBZI3fpi1Um/
  note: dice
  kind: tattoo
- url: https://www.instagram.com/p/DA-cL1Ii7G7/
  note: art contrast, scissors
  kind: tattoo
- url: https://www.instagram.com/p/C7wP_UiinAH/
  note: hand and demon
  kind: tattoo
- url: https://www.instagram.com/p/C-SbhUMCwBP/
  note: frog and cloud
  kind: tattoo
- url: https://www.instagram.com/p/C5izBwMIB28/
  note: sun and robe
  kind: tattoo
- url: https://www.instagram.com/p/C27xuW8iG5T/
  note: escher
  kind: tattoo
- url: https://www.instagram.com/p/CzFSqRAvfKa/
  note: idk but so cool, tall priestlike
  kind: tattoo
  starred: true
- url: https://www.instagram.com/p/CrdsEd1q0pe/
  note: fractured reflection
  kind: tattoo
  starred: true
- url: https://www.instagram.com/p/DXHX6jQiDdR/
  note: misc
  kind: tattoo
- url: https://www.instagram.com/p/DPUAhmSiikH/
  note: shadow puppet
  kind: tattoo
```

## Angel Motif

```yaml
- url: https://www.instagram.com/p/C1iqkU1NDR2/
  note: pontificating angel
  kind: tattoo
- url: https://www.instagram.com/p/DXR7_PuEuWR/?img_index=1
  note: sisyphus
  kind: tattoo
```

## Architecture / Buildings

```yaml
- url: https://www.instagram.com/p/C6DqNqEiJKA/
  kind: tattoo
- url: https://www.instagram.com/p/C2oluh9CiDD/
  note: duality, churchlike
  kind: tattoo
- url: https://www.instagram.com/p/C2xaCIxuJe0/
  note: lamppost
  kind: tattoo
- url: https://www.instagram.com/p/C11TAQiix6R/
  note: skull and door
  kind: tattoo
- url: https://www.instagram.com/p/CwSATqtLngy/
  note: building
  kind: tattoo
- url: https://www.instagram.com/p/Cv9pvNTrp_I/
  note: sun over cliff village
  kind: tattoo
  starred: true
- url: https://www.instagram.com/p/Cu_1eK5s39s/
  note: lots of building
  kind: tattoo
- url: https://www.instagram.com/p/DX7G4LujAB_/
  note: sinking statue of liberty
  kind: tattoo
  starred: true
- url: https://www.instagram.com/p/DUbucGXku6e/
  note: inspo sketch, floating building
  kind: art
- url: https://www.instagram.com/p/DVjYy7mD4n5/
  note: inspo sketch
  kind: art
- url: https://www.instagram.com/p/DUbXyGYloAQ/?img_index=1
  note: cool triple church
  kind: tattoo
```

## Animal

```yaml
- url: https://www.instagram.com/p/C6hAIXEPbYD/
  note: frog, color
  kind: tattoo
- url: https://www.instagram.com/p/C6t7NGeuwQP/
  note: cat, brain
  kind: tattoo
- url: https://www.instagram.com/p/C35RySZviiY/
  note: cat and moon
  kind: tattoo
- url: https://www.instagram.com/p/CzWST9piHKC/
  note: tattoo cats
  kind: tattoo
- url: https://www.instagram.com/p/Cv2RJ_sL1-7/
  note: angel/demon cat
  kind: art
- url: https://www.instagram.com/p/DXuY3thDDlI/
  note: 3 cats in a trench coat
  kind: tattoo
- url: https://www.instagram.com/p/DVEGunGDL8O/
  note: silly cat sketch
  kind: art
- url: https://www.instagram.com/p/DPvllx1D9U7/
  note: cat bat
  kind: tattoo
- url: https://www.instagram.com/p/DP_DT2ejpuM/
  note: cool ass cats
  kind: tattoo
  starred: true
- url: https://www.instagram.com/p/DJeuv_vJo7J/?img_index=1
  note: cool cat texturing
  kind: tattoo
- url: https://www.instagram.com/p/DB3nlVduNtu/
  note: bat and branches
  kind: tattoo
```

## Body

```yaml
- url: https://www.instagram.com/p/C2p0fOcPIJf/
  note: clasping hands
  kind: tattoo
```

## Lookbooks

```yaml
- url: https://www.instagram.com/p/C3lBo2br9Qw/
  note: lookbook of various
  kind: lookbook
- url: https://www.instagram.com/p/Ctbu5DwvEuI/
  note: kind of classic style
  kind: lookbook
- url: https://www.instagram.com/p/C1fuig3RgDq/
  note: spiky
  kind: lookbook
- url: https://www.instagram.com/p/CzSAEH6pTkt/?img_index=6
  note: simple lookbook
  kind: lookbook
- url: https://www.instagram.com/p/DXzCedEEcK0/
  note: kind of random, medieval theme, cool building
  kind: lookbook
  starred: true
- url: https://www.instagram.com/francesco.lucidi__/p/DXHO_1LjYGC/
  note: cool building
  kind: lookbook
```

```

```
