import time
from atheriz.objects.nodes import Node, NodeGrid, NodeArea
from atheriz.utils import get_points_in_sphere


def _build_sparse_area(name="SphereTest"):
    area = NodeArea(name=name)
    for z in (0, 10):
        grid = NodeGrid(z=z)
        for x in range(0, 25, 3):
            for y in range(0, 25, 3):
                grid.nodes[(x, y)] = Node(coord=(name, x, y, z))
        area.add_grid(grid)
    return area


def test_get_nodes_in_sphere_correctness_and_speed():
    area = _build_sparse_area()
    center = (12, 12, 5)
    radius = 12

    coords = get_points_in_sphere(center, radius, ignore_center=True)

    t0 = time.perf_counter()
    old_nodes = area.get_nodes(coords)
    old_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    new_nodes = area.get_nodes_in_sphere(center, radius, ignore_center=True)
    new_time = time.perf_counter() - t0

    old_set = set(n.coord for n in old_nodes)
    new_set = set(n.coord for n in new_nodes)
    assert old_set == new_set, f"Mismatch: old={len(old_set)} new={len(new_set)}"

    print(f"\n[Sphere benchmark] radius={radius}, sphere coords={len(coords)}")
    print(
        f"  old (get_points_in_sphere + get_nodes): {old_time * 1000:.3f} ms -> {len(old_nodes)} nodes"
    )
    print(
        f"  new (get_nodes_in_sphere):              {new_time * 1000:.3f} ms -> {len(new_nodes)} nodes"
    )
    print(f"  speedup: {old_time / new_time:.2f}x")


def test_get_rays_in_sphere_correctness_and_speed():
    area = _build_sparse_area()
    center = (12, 12, 5)
    radius = 12

    coords = get_points_in_sphere(center, radius, ignore_center=True)

    t0 = time.perf_counter()
    old_nodes = area.get_nodes(coords)
    old_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    new_nodes = area.get_nodes_in_sphere(center, radius, ignore_center=True)
    new_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    rays = area.get_rays_in_sphere(center, radius, ignore_center=True)
    rays_time = time.perf_counter() - t0

    old_set = set(n.coord for n in old_nodes)
    new_set = set(n.coord for n in new_nodes)
    rays_flat = [n for ray in rays for n in ray]
    rays_set = set(n.coord for n in rays_flat)

    assert old_set == new_set == rays_set, (
        f"Mismatch: old={len(old_set)} new={len(new_set)} rays={len(rays_set)}"
    )

    assert len(rays_flat) == len(rays_set), "Duplicate nodes in rays"

    for ray in rays:
        dists = []
        for n in ray:
            nx, ny, nz = n.coord[1], n.coord[2], n.coord[3]
            dx, dy, dz = nx - center[0], ny - center[1], nz - center[2]
            dists.append(dx * dx + dy * dy + dz * dz)
        assert dists == sorted(dists), f"Ray not sorted by distance: {dists}"

    avg_len = len(rays_flat) / len(rays) if rays else 0
    print(f"\n[Ray benchmark] radius={radius}, sphere coords={len(coords)}")
    print(
        f"  old (get_points_in_sphere + get_nodes): {old_time * 1000:.3f} ms -> {len(old_nodes)} nodes"
    )
    print(
        f"  new (get_nodes_in_sphere):              {new_time * 1000:.3f} ms -> {len(new_nodes)} nodes"
    )
    print(
        f"  rays (get_rays_in_sphere):              {rays_time * 1000:.3f} ms -> {len(rays)} rays, {len(rays_flat)} nodes"
    )
    print(f"  avg ray length: {avg_len:.2f}")


def test_get_nodes_in_sphere_ignore_center():
    area = NodeArea(name="CenterTest")
    grid = NodeGrid(z=0)
    grid.nodes[(0, 0)] = Node(coord=("CenterTest", 0, 0, 0))
    grid.nodes[(1, 0)] = Node(coord=("CenterTest", 1, 0, 0))
    area.add_grid(grid)

    with_center = area.get_nodes_in_sphere((0, 0, 0), 2)
    without_center = area.get_nodes_in_sphere((0, 0, 0), 2, ignore_center=True)

    assert len(with_center) == 2
    assert len(without_center) == 1


def test_get_nodes_in_sphere_no_grids():
    area = NodeArea(name="EmptyTest")
    result = area.get_nodes_in_sphere((0, 0, 0), 10)
    assert result == []
