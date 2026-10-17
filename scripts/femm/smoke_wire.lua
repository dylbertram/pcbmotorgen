-- Smoke test: field of a long round wire, B = μ0·I/(2π·r) outside the wire.
-- Usage: scripts/femm/run_femm.sh scripts/femm/smoke_wire.lua <out_dir>
-- Writes <out_dir>/smoke_wire.csv with r_mm, femm_T, analytic_T, rel_err.
out = arg1 or "."
I = 10        -- A
a = 1         -- wire radius, mm
Rb = 100      -- outer A = 0 boundary, mm (concentric, so it does not disturb B)

newdocument(0)
mi_probdef(0, "millimeters", "planar", 1e-9, 1000, 30)
mi_addmaterial("Air", 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0)
mi_addmaterial("Cu", 1, 1, 0, 0, 58, 0, 0, 1, 0, 0, 0)
mi_addcircprop("w", I, 1)
mi_addboundprop("A0", 0, 0, 0, 0, 0, 0, 0, 0, 0)

function circle(r)
  mi_addnode(-r, 0); mi_addnode(r, 0)
  mi_addarc(-r, 0, r, 0, 180, 2); mi_addarc(r, 0, -r, 0, 180, 2)
end
circle(a); circle(Rb)
mi_selectarcsegment(0, Rb); mi_selectarcsegment(0, -Rb)
mi_setarcsegmentprop(2, "A0", 0, 0); mi_clearselected()

mi_addblocklabel(0, 0); mi_selectlabel(0, 0)
mi_setblockprop("Cu", 0, 0.05, "w", 0, 0, 1); mi_clearselected()
mi_addblocklabel(0, 50); mi_selectlabel(0, 50)
mi_setblockprop("Air", 0, 1, "", 0, 0, 0); mi_clearselected()

mi_saveas(out .. "/smoke_wire.fem")
mi_analyze(1)
mi_loadsolution()

mu0 = 4e-7 * PI
h = openfile(out .. "/smoke_wire.csv", "w")
write(h, "r_mm,femm_T,analytic_T,rel_err\n")
radii = {5, 10, 20, 40}
for i = 1, getn(radii) do
  r = radii[i]
  -- average over a few angles to wash out mesh noise
  s = 0
  for k = 0, 7 do
    th = k * PI / 4  -- FEMM's Lua is built with RADIANS
    a_, bx, by = mo_getpointvalues(r * cos(th), r * sin(th))
    s = s + sqrt(bx * bx + by * by)
  end
  b = s / 8
  ba = mu0 * I / (2 * PI * r * 1e-3)
  write(h, r, ",", b, ",", ba, ",", (b - ba) / ba, "\n")
end
closefile(h)
quit()
