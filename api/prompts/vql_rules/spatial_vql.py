SPATIAL_VQL = """
Apart from the spatial functions from the SQL Standard (SQL/MM Spatial / OGC SFA), VQL also supports these:

    - ST_AREA_METERS(wkb, code). This function returns the area of wkb. The units of the result are square meters. The code identifies the CRS of the geometry.
    - ST_BUFFER_METERS(wkt, code, <distance:double>). Returns a new geometry that covers all points within a given distance from the input geometry. The code identifies the CRS of the geometry. The unit of distance is meters.
    - ST_CREATE_POINT(<x:DOUBLE>, <y:DOUBLE). Creates a point, the parameters are the abscissa(x) and the ordinate(y), which define the location of a point in two-dimensional rectangular space.
    - ST_DISTANCE_METERS(wkb1|wkt1, code1, wkb2|wkt1, code2). Returns the minimum distance between the geometry wkb1/wkt1 and the geometry wkb2/wkt2 expressed in meters. The codes identify the CRS of each geometry.

        If any of the CRS of the inputs are different to WGS84, then they are projected to WGS84, and when the two geometries are in WGS84, the orthodromic distance between the two geometries is calculated.
        For example:
            ST_DISTANCE_METERS('POINT(43.37 -8.41)','EPSG:4326', 'POINT(43.50 -8.22)','EPSG:4326')
            ST_DISTANCE_METERS('POINT(547800.41 4802073)','EPSG:32629', 'POINT (563058.68 4816636.85)','EPSG:32629')

            These examples are equivalents, their operation is on the two same points, expressed in WGS84 and in UTM zone 29N respectively, and the result will be:

            21100.76

    - ST_GEOM_TO_STRUCT(wkb|wkt). Parses a blob (if wkb) or text (if wkt) value that represents a geometry and converts it into a structural representation of the geometry in terms of register and arrays.
    - ST_LENGTH_METERS(wkb, <code:string>). Returns the length of wkb/wkt, the units of the result are meters.
    - ST_TRANSFORM(wkb, <source_code:string>, <target_code:string). Transforms a geometry from one CRS to another CRS.
    - ST_WKBTOWKT(wkb). Transforms a well-known binary (wkb) into a well-known text (wkt).
    - ST_WKTTOWKB(wkt). Transforms a well-known text (wkt) into a well-known binary (wkb).

The CRS codes in VQL need to include the authority (usually EPSG), like 'EPSG:1234', 'AUTO:42001'"""
