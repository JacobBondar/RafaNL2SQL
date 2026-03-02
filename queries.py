FINAL_SQL = """
            SELECT * FROM (
                {base_sql}
            )
            WHERE {actual_sql_col} IN ('{ids_string}')
            AND ROWNUM <= {MAX_ROWS_QUERY}
        """

ALL_REPORTS = """
        SELECT DISTINCT d.doc_id, d.doc_name, d.doc_description,
               o.obj_id, o.obj_name, o.sobj_ext_table
        FROM EUL4_US.eul5_documents d
        JOIN EUL4_US.eul5_elem_xrefs x ON x.ex_from_id = d.doc_id
        JOIN EUL4_US.eul5_expressions e ON x.ex_to_id = e.exp_id
        JOIN EUL4_US.eul5_objs o ON e.it_obj_id = o.obj_id
        WHERE x.ex_from_type = 'DOC'
          AND d.doc_created_by = '#1140'
          AND o.obj_created_by = '#1140'
          AND ({like_conditions})
        ORDER BY d.doc_name, o.obj_name
    """

COLUMN_NAMES = """
            SELECT COLUMN_NAME
            FROM all_tab_columns
            WHERE TABLE_NAME = :table_name
        """

GET_CHUNKS = """
        SELECT seg_chunk1, seg_chunk2, seg_chunk3, seg_chunk4
        FROM EUL4_US.EUL5_SEGMENTS
        WHERE seg_obj_id = :obj_id
          AND seg_created_by = '#1140'
        ORDER BY seg_id
    """

GET_REAL_NAMES = """
            SELECT exp_id, exp_name 
            FROM EUL4_US.EUL5_EXPRESSIONS 
            WHERE exp_id IN ({ids_str})
        """

GET_PRODUCTS_NAMES = """
        SELECT DISTINCT SEGMENT1
        FROM MTL_SYSTEM_ITEMS_B
        WHERE (UPPER(DESCRIPTION) LIKE :term OR SEGMENT1 LIKE :term)
        """

SELECT_ALL_TABLE = """
        SELECT * FROM {table_name}
        """

SELECT_EMPTY_STRUCTURE = """
        SELECT * FROM ({base_sql}) WHERE 1=0
        """