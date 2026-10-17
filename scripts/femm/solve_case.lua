-- Generic 2-D planar magnetostatic / time-harmonic case for the t707 check.
-- Usage: scripts/femm/run_femm.sh scripts/femm/solve_case.lua <case.lua> <out_dir>
--
-- <case.lua> sets a global table `case` (written by femm_backplane.py):
--   name      file stem for outputs
--   period    domain width [mm]; x in [-period/2, period/2], periodic edges
--   freq      0 for magnetostatics, else Hz (time-harmonic, eddy currents on)
--   materials { {name, mu, sigma (MS/m), hc (A/m), j (MA/m^2)}, ... }
--   bands     full-width horizontal bands, bottom to top:
--             { {y0, y1, mat, mesh (0 = auto), group}, ... }  (contiguous)
--   rects     rectangles inside one band:
--             { {x0, x1, y0, y1, mat, mesh, group, magdir}, ... }
--   labels    extra region labels (air pockets cut off by rectangles):
--             { {x, y, mat, mesh, group}, ... }
--   lines     B sample lines: { {name, y, n}, ... }
--   points    B sample points: { {name, x, y}, ... }
-- Groups: 1 = sources (A.J integral), 2 = stack/housing, 3 = magnets.
-- Writes <out_dir>/<name>.out as "key value" lines.
dofile(arg1)
out = arg2
P = case.period
xl = -P / 2
xr = P / 2

newdocument(0)
mi_probdef(case.freq, "millimeters", "planar", 1e-9, 1000, 30)

for i = 1, getn(case.materials) do
  local m = case.materials[i]
  mi_addmaterial(m.name, m.mu, m.mu, m.hc or 0, m.j or 0, m.sigma or 0, 0, 0, 1, 0, 0, 0)
end
mi_addboundprop("A0", 0, 0, 0, 0, 0, 0, 0, 0, 0)

-- Band interfaces: full-width lines.
nb = getn(case.bands)
ylev = {}
for i = 1, nb do ylev[i] = case.bands[i].y0 end
ylev[nb + 1] = case.bands[nb].y1
for i = 1, nb + 1 do
  mi_addnode(xl, ylev[i]); mi_addnode(xr, ylev[i])
end
for i = 1, nb + 1 do mi_addsegment(xl, ylev[i], xr, ylev[i]) end
for i = 1, nb do
  mi_addsegment(xl, ylev[i], xl, ylev[i + 1])
  mi_addsegment(xr, ylev[i], xr, ylev[i + 1])
end

-- Rectangles (never touch the periodic edges).
for i = 1, getn(case.rects) do
  local r = case.rects[i]
  mi_drawrectangle(r.x0, r.y0, r.x1, r.y1)
end

-- Boundaries: A = 0 top and bottom, one periodic pair per band edge.
mi_selectsegment(0, ylev[1]); mi_selectsegment(0, ylev[nb + 1])
mi_setsegmentprop("A0", 0, 1, 0, 0); mi_clearselected()
for i = 1, nb do
  local name = "per" .. i
  local ym = (ylev[i] + ylev[i + 1]) / 2
  mi_addboundprop(name, 0, 0, 0, 0, 0, 0, 0, 0, 4)
  mi_selectsegment(xl, ym); mi_setsegmentprop(name, 0, 1, 0, 0); mi_clearselected()
  mi_selectsegment(xr, ym); mi_setsegmentprop(name, 0, 1, 0, 0); mi_clearselected()
end

function block(x, y, mat, mesh, group, magdir)
  mi_addblocklabel(x, y); mi_selectlabel(x, y)
  if mesh and mesh > 0 then
    mi_setblockprop(mat, 0, mesh, "", magdir or 0, group or 0, 0)
  else
    mi_setblockprop(mat, 1, 0, "", magdir or 0, group or 0, 0)
  end
  mi_clearselected()
end
-- Band labels sit next to the left edge; rectangles keep clear of it.
for i = 1, nb do
  local b = case.bands[i]
  block(xl + 0.01 * P / 12, (b.y0 + b.y1) / 2, b.mat, b.mesh, b.group, 0)
end
for i = 1, getn(case.rects) do
  local r = case.rects[i]
  block((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2, r.mat, r.mesh, r.group, r.magdir)
end
for i = 1, getn(case.labels or {}) do
  local l = case.labels[i]
  block(l.x, l.y, l.mat, l.mesh, l.group, 0)
end

mi_saveas(out .. "\\" .. case.name .. ".fem")
mi_analyze(1)
mi_loadsolution()

h = openfile(out .. "\\" .. case.name .. ".out", "w")
function put(k, v) write(h, k, " ", v, "\n") end
function cput(k, z) put(k .. "_re", re(z)); put(k .. "_im", im(z)) end

function integral(group, kind)
  mo_groupselectblock(group)
  local v = mo_blockintegral(kind)
  mo_clearblock()
  return v
end
function has_group(g)
  for i = 1, getn(case.bands) do if case.bands[i].group == g then return 1 end end
  for i = 1, getn(case.rects) do if case.rects[i].group == g then return 1 end end
  return nil
end

if has_group(1) then cput("AJ_sources", integral(1, 0)) end
if has_group(2) then put("Fy_stack", re(integral(2, 19))) end
if has_group(3) then put("Fy_magnets", re(integral(3, 19))) end
mo_groupselectblock(); put("energy_total", re(mo_blockintegral(2))); mo_clearblock()

-- Lines: By fundamental (cos and sin parts, wavenumber 2*pi/P) and samples.
for i = 1, getn(case.lines) do
  local l = case.lines[i]
  local c, s = 0, 0
  for j = 0, l.n - 1 do
    local x = xl + (j + 0.5) * P / l.n
    local a, b1, b2 = mo_getpointvalues(x, l.y)
    local th = 2 * PI * (x - xl) / P   -- FEMM's Lua trig uses radians
    c = c + re(b2) * cos(th); s = s + re(b2) * sin(th)
  end
  put(l.name .. "_By1", sqrt(c * c + s * s) * 2 / l.n)
end
for i = 1, getn(case.points) do
  local p = case.points[i]
  local a, b1, b2 = mo_getpointvalues(p.x, p.y)
  put(p.name .. "_Bx", re(b1)); put(p.name .. "_By", re(b2))
end
closefile(h)
