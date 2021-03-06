from random import Random

from scipy.spatial import Voronoi, Delaunay
import numpy as np
import math

import map_gen_2.util.vector_util as vect


class Generator:
    init_points = np.empty((0, 2))
    voronoi = None
    delaunay = None

    height = None
    width = None
    num_points = None
    rand = None

    sorted_water_dps = []  # All water d_points. Sorted into individual water arrays.
    processed_water_dps = []  # Water d_points that have been made into water polygons.
    all_water_dps = []  # All water d_point indexes, unsorted.
    water_edge_dps = []
    water_polys = []
    water_edges = []

    all_mountain_dps = []
    sorted_mountain_dps = []

    hill_dps = []
    forest_dps = []
    marsh_dps = []

    sorted_river_dps = []
    all_river_dps = []
    river_points = []

    debug_points = []

    def __init__(self, height=720, width=1280, num_points=1000, seed=None, regularity=2):

        self.height = height

        self.width = width
        self.num_points = num_points

        self.rand = Random()
        if seed is not None:
            self.rand.seed(seed)

        print("Generating geometry...")
        self.gen_geometry(regularity)

        print("Generating water...")
        self.gen_water(num_points / 4, 0.025)

        print("Generating mountains...")
        self.gen_mountains(num_points / 40, 0.3)

        print("Generating hills...")
        self.gen_hills(num_points / 75, 0.0001)

        print("Generating forests...")
        self.gen_forests(num_points / 15, 0.001)

        print("Generating rivers...")
        self.gen_rivers(round(num_points / 500))

    def gen_geometry(self, regularity):
        self.gen_random_init_points()

        self.delaunay = Delaunay(self.init_points)
        self.voronoi = Voronoi(self.init_points)

        for i in range(regularity):
            self.gen_centroid_init_points()
            self.delaunay = Delaunay(self.init_points)
            if len(self.delaunay.coplanar) > 0:
                raise ValueError("Delaunay triangulation was coplanar. Try a lower regularity or different seed.")
            self.voronoi = Voronoi(self.init_points)

    def gen_random_init_points(self):
        for i in range(self.num_points):
            self.init_points = np.insert(self.init_points, len(self.init_points),
                                         [self.rand.random() * self.width, self.rand.random() * self.height], axis=0)

    def gen_centroid_init_points(self):
        """ Generates initial points based on the centroids of the Voronoi diagram. """
        if self.voronoi is None:
            raise ValueError("Voronoi diagram is None")

        self.init_points = np.empty((0, 2))
        for region in self.voronoi.regions:
            if len(region) == 0:
                continue
            num_points = float(len(region))
            sum_coord = np.array([0.0, 0.0])
            for idx in region:
                if idx != -1:
                    sum_coord += self.voronoi.vertices[idx]
            coord = [sum_coord[0] / num_points, sum_coord[1] / num_points]

            self.init_points = np.insert(self.init_points, len(self.init_points), coord, axis=0)

    def check_used(self, dp_idx):
        return dp_idx in self.all_water_dps \
               or dp_idx in self.all_mountain_dps \
               or dp_idx in self.hill_dps \
               or dp_idx in self.forest_dps \
               or dp_idx in self.marsh_dps

    def check_near_obstacle(self, dp_idx, depth=2, water=True, mountain=False):
        neighbours = [dp_idx]
        for i in range(depth):
            new_neighbours = neighbours.copy()
            for n in neighbours:
                this_ns = self.get_delaunay_neighbours(n)
                for this_n in this_ns:
                    if this_n not in new_neighbours:
                        new_neighbours.append(this_n)
            neighbours = new_neighbours
        for n in neighbours:
            if n in self.all_water_dps and water:
                return True
            if n in self.all_mountain_dps and mountain:
                return True
        return False

    def grow_area_from_point(self, max_regions, init_point_idx, max_iterations=100000, avoid_depth=0):
        area_d_point_idxs = [init_point_idx]
        iterations = 0
        while len(area_d_point_idxs) < max_regions:
            iterations += 1
            if iterations < max_iterations:
                area_d_point_idx = self.rand.choice(area_d_point_idxs)
                neighbour_idxs = self.get_delaunay_neighbours(area_d_point_idx)
                to_add = self.rand.choice(neighbour_idxs)
                if area_d_point_idxs.count(to_add) > 0 or self.check_used(to_add) or (
                            avoid_depth and self.check_near_obstacle(to_add, avoid_depth, True, True)):
                    continue
                else:
                    area_d_point_idxs.append(to_add)
            else:
                all_neighbours = []
                for p_idx in area_d_point_idxs:
                    this_ns = self.get_delaunay_neighbours(p_idx)
                    for n in this_ns:
                        if not n in area_d_point_idxs:
                            all_neighbours.append(n)
                unexpanded = True
                for n in all_neighbours:
                    if not self.check_used(n):
                        area_d_point_idxs.append(n)
                        unexpanded = False
                        break
                if unexpanded:
                    return area_d_point_idxs
        return area_d_point_idxs

    def grow_d_line_from_point(self, max_points, init_point_idx, straightish=True, avoid_water_depth=2):
        line_d_point_idxs = [init_point_idx]
        while len(line_d_point_idxs) < max_points:
            neighbour_idxs = self.get_delaunay_neighbours(line_d_point_idxs[-1])

            if straightish and len(line_d_point_idxs) > 1:
                last_vect = vect.subtract(self.delaunay.points[line_d_point_idxs[-1]],
                                          self.delaunay.points[line_d_point_idxs[-2]])
                max_angle = 0
                to_add = -1
                for n in neighbour_idxs:
                    viable = not self.check_used(n) and not (
                        self.check_near_obstacle(n,
                                                 avoid_water_depth) and avoid_water_depth) and line_d_point_idxs.count(
                        n) == 0
                    if not viable:
                        continue

                    n_vect = vect.subtract(self.delaunay.points[line_d_point_idxs[-1]],
                                           self.delaunay.points[n])
                    this_angle = vect.angle(last_vect, n_vect)
                    if this_angle > max_angle:
                        max_angle = this_angle
                        to_add = n
                if to_add == -1:
                    return line_d_point_idxs
                else:
                    line_d_point_idxs.append(to_add)

            else:
                # Don't get trapped.
                all_used = True
                for n in neighbour_idxs:
                    if not self.check_used(n) and n not in line_d_point_idxs:
                        all_used = False
                if all_used:
                    return line_d_point_idxs

                to_add = self.rand.choice(neighbour_idxs)
                if line_d_point_idxs.count(to_add) > 0 or self.check_used(to_add):
                    continue
                else:
                    line_d_point_idxs.append(to_add)
        return line_d_point_idxs

    def grow_line_from_to(self, d_point_start, d_point_end, reset_start_on_obstacle=True):
        start_point = self.delaunay.points[d_point_start]
        line_points = [start_point]
        line_dps = [d_point_start]
        end_point = self.delaunay.points[d_point_end]

        finished = False
        while not finished and len(line_dps) < 500:
            last_point = line_points[-1]
            neighbours = self.get_delaunay_neighbours(line_dps[-1])
            min_angle = math.inf
            to_add = -1
            for n in neighbours:
                if n == d_point_end:
                    to_add = n
                    break
                n_point = self.delaunay.points[n]
                last_to_n = vect.subtract(n_point, last_point)
                last_to_end = vect.subtract(end_point, last_point)
                angle = vect.angle(last_to_end, last_to_n)
                if angle < min_angle and n not in line_dps:
                    min_angle = angle
                    to_add = n
            if to_add != -1:
                if self.check_near_obstacle(to_add, 0, True, False) and reset_start_on_obstacle:
                    line_dps = [to_add]
                    line_points = [self.delaunay.points[to_add]]
                else:
                    line_dps.append(to_add)
                    line_points.append(self.delaunay.points[to_add])
            if to_add == d_point_end or to_add == -1 or to_add in self.all_river_dps:
                finished = True
        return line_dps

    def get_delaunay_neighbours(self, point_idx):
        indices = self.delaunay.vertex_neighbor_vertices[0]
        indptr = self.delaunay.vertex_neighbor_vertices[1]
        neighbour_idxs = indptr[indices[point_idx]:indices[point_idx + 1]]
        return neighbour_idxs

    def get_shared_line(self, p1_idx, p2_idx):
        if p2_idx in self.get_delaunay_neighbours(p1_idx):
            points = []
            r1 = self.voronoi.regions[self.voronoi.point_region[p1_idx]]
            r2 = self.voronoi.regions[self.voronoi.point_region[p2_idx]]

            for v1 in r1:
                for v2 in r2:
                    if v1 == v2:
                        points.append(v1)
            return points

    def get_region_idxs_from_d_points(self, d_points):
        regions = []
        for p in d_points:
            regions.append(self.voronoi.point_region[p])
        return regions

    def gen_water_points(self, size):
        point = self.rand.randrange(0, len(self.init_points))
        while point in self.all_water_dps:
            point = self.rand.randrange(0, len(self.init_points))
        d_points = self.grow_area_from_point(size, point)
        self.sorted_water_dps.append(d_points)
        self.all_water_dps.extend(d_points)

    def gen_water_polygon(self, d_points):
        for d_p in d_points:
            if d_p in self.processed_water_dps:
                continue
            else:
                self.processed_water_dps.append(d_p)
            region_idx = self.voronoi.point_region[d_p]
            region = self.voronoi.regions[region_idx]
            region_poly = []

            edge_lines = []

            neighbours = self.get_delaunay_neighbours(d_p)
            for i in range(len(neighbours)):
                n = neighbours[i]
                if n not in self.all_water_dps:
                    if d_p not in self.water_edge_dps:
                        self.water_edge_dps.append(d_p)
                    edge_lines.append(self.get_shared_line(d_p, n))

            for i in range(len(region)):
                v_idx = region[i]
                if v_idx == -1:
                    continue
                this_vert = self.voronoi.vertices[v_idx]
                next_i = i + 1
                if i + 1 == len(region):
                    next_i = 0
                expanded = False
                for line in edge_lines:
                    if v_idx in line and region[next_i] in line:
                        if region[next_i] == -1:
                            continue
                        next_vert = self.voronoi.vertices[region[next_i]]
                        line_segment = [this_vert, next_vert]
                        for s in range(3):
                            new_line_segment = []
                            for j in range(len(line_segment)):
                                new_line_segment.append(line_segment[j])
                                if j + 1 < len(line_segment):
                                    new_line_segment.append(
                                        vect.split_line(line_segment[j], line_segment[j + 1], self.rand))
                            line_segment = new_line_segment

                        self.water_edges.append(line_segment)
                        for vert in line_segment:
                            region_poly.append(vert)
                        expanded = True

                if not expanded:
                    region_poly.append(this_vert)

            self.water_polys.append(region_poly)

    def gen_water(self, total_size, small_fract):
        """
        Generates water for the map.
        :param total_size: Total number of water regions.
        :param small_fract: Fraction of total size that is small water.
        """
        small_quota = small_fract * total_size
        large_quota = total_size - small_quota

        large_min = math.floor(self.num_points * 0.08)
        large_max = math.ceil(self.num_points * 0.15)

        small_max = math.ceil(self.num_points * 0.0025)

        if large_quota < large_min:
            print("Warning: No large water will be generated. Consider reducing small_fract.")

        large_used = 0
        while large_used < large_quota:
            size = self.rand.randint(large_min, large_max + 1)
            self.gen_water_points(size)
            large_used += size

        small_used = 0
        while small_used < small_quota:
            size = self.rand.randint(0, small_max + 1)
            self.gen_water_points(size)
            small_used += size

        for dps in self.sorted_water_dps:
            self.gen_water_polygon(dps)

    def gen_mountains(self, total_points, max_length_fract):
        max_length = math.ceil(math.sqrt(self.num_points) * max_length_fract)
        total_used = 0
        while total_used < total_points:
            length = self.rand.randint(1, max_length + 1)
            start_dp_idx = self.rand.randint(0, self.num_points)
            while self.check_used(start_dp_idx) or self.check_near_obstacle(start_dp_idx):
                start_dp_idx = self.rand.randint(0, self.num_points)
            line = self.grow_d_line_from_point(length, start_dp_idx)
            self.all_mountain_dps.extend(line)
            self.sorted_mountain_dps.append(line)
            total_used += length

    def gen_hills(self, total_points, max_size_fract):
        max_size = math.ceil(self.num_points * max_size_fract)
        total_used = 0
        while total_used < total_points:
            size = self.rand.randint(1, max_size + 1)
            start_dp_idx = self.rand.randint(0, self.num_points)
            while self.check_used(start_dp_idx) or self.check_near_obstacle(start_dp_idx, 2, True, True):
                start_dp_idx = self.rand.randint(0, self.num_points)
            area = self.grow_area_from_point(size, start_dp_idx, avoid_depth=2)
            self.hill_dps.extend(area)
            total_used += size

    def gen_forests(self, total_points, max_size_fract):
        max_size = math.ceil(self.num_points * max_size_fract)
        total_used = 0
        while total_used < total_points:
            size = self.rand.randint(1, max_size + 1)
            start_dp_idx = self.rand.randint(0, self.num_points)
            while self.check_used(start_dp_idx) or self.check_near_obstacle(start_dp_idx, 1, True, True):
                start_dp_idx = self.rand.randint(0, self.num_points)
            area = self.grow_area_from_point(size, start_dp_idx, avoid_depth=1)
            self.forest_dps.extend(area)
            total_used += size

    def gen_rivers(self, num_rivers):
        for r in range(num_rivers):
            w_edge_dp = self.rand.choice(self.water_edge_dps)
            min_distance = math.inf
            m_dp_target = -1
            for m_dp in self.all_mountain_dps:
                dist = vect.dist(self.delaunay.points[w_edge_dp], self.delaunay.points[m_dp])
                if dist < min_distance:
                    m_dp_target = m_dp
                    min_distance = dist
            line_dps = self.grow_line_from_to(w_edge_dp, m_dp_target)

            if len(line_dps) < 2:
                continue

            self.all_river_dps.extend(line_dps)

            start_corner_verts = self.voronoi.regions[self.voronoi.point_region[line_dps[0]]]
            land_point = self.delaunay.points[line_dps[1]]
            min_distance = math.inf
            water_edge_point = None
            for v_idx in start_corner_verts:
                v_point = self.voronoi.vertices[v_idx]
                dist = vect.dist(land_point, v_point)
                if dist < min_distance:
                    water_edge_point = v_point
                    min_distance = dist

            r_points = [water_edge_point]
            for i in range(1, len(line_dps)):
                if line_dps[i] in self.all_mountain_dps:
                    continue
                r_points.append(self.delaunay.points[line_dps[i]])
            self.river_points.append(r_points)
