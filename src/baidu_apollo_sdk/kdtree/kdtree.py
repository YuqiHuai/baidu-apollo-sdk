"""modules/common/math/aaboxkdtree2d.h"""

from shapely.geometry import Point, Polygon, box
from shapely.geometry.base import BaseGeometry

from .kdtree_node import KDTreeNode
from .kdtree_params import KDTreeParams


class KDTree:
    root: KDTreeNode | None = None

    def __init__(
        self, objects: list[BaseGeometry], params: KDTreeParams
    ) -> None:
        if not objects:
            raise ValueError("No objects provided")
        self.root = KDTreeNode(objects, params, 0)

    def get_nearest_object(self, point: Point) -> BaseGeometry:
        if self.root is None:
            raise RuntimeError("KDTree has not been initialized")
        nearest = self.root.get_nearest_object(point)
        if nearest is None:
            raise RuntimeError("KDTree did not find a nearest object")
        return nearest

    def get_objects(self, point: Point, distance: float) -> list[BaseGeometry]:
        if self.root is None:
            return []
        return self.root.get_objects(point, distance)

    def get_bounding_box(self) -> Polygon:
        if self.root is None:
            return box(0, 0, 0, 0)
        return self.root.get_bounding_box()
