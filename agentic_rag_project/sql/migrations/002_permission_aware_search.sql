-- Permission-aware search migration
-- Adds Nextcloud file-ID filtering without modifying existing tables/data.

CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding vector(1536),
    match_count INT DEFAULT 10,
    p_allowed_groups TEXT[] DEFAULT NULL,
    p_allowed_nextcloud_file_ids TEXT[] DEFAULT NULL
)
RETURNS TABLE (
    chunk_id UUID,
    document_id UUID,
    content TEXT,
    similarity FLOAT,
    metadata JSONB,
    document_title TEXT,
    document_source TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        c.document_id,
        c.content,
        (1 - (c.embedding <=> query_embedding))::double precision AS similarity,
        c.metadata,
        d.title AS document_title,
        d.source AS document_source
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE c.embedding IS NOT NULL
      AND (
        p_allowed_groups IS NULL
        OR d.metadata->>'allowed_group' = ANY(p_allowed_groups)
      )
      AND (
        p_allowed_nextcloud_file_ids IS NULL
        OR (
            d.metadata ? 'nextcloud_file_id'
            AND d.metadata->>'nextcloud_file_id' = ANY(p_allowed_nextcloud_file_ids)
        )
      )
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;


CREATE OR REPLACE FUNCTION hybrid_search(
    query_embedding vector(1536),
    query_text TEXT,
    match_count INT DEFAULT 10,
    text_weight FLOAT DEFAULT 0.3,
    p_allowed_groups TEXT[] DEFAULT NULL,
    p_allowed_nextcloud_file_ids TEXT[] DEFAULT NULL
)
RETURNS TABLE (
    chunk_id UUID,
    document_id UUID,
    content TEXT,
    combined_score FLOAT,
    vector_similarity FLOAT,
    text_similarity FLOAT,
    metadata JSONB,
    document_title TEXT,
    document_source TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH vector_results AS (
        SELECT
            c.id AS chunk_id,
            c.document_id,
            c.content,
            (1 - (c.embedding <=> query_embedding))::double precision AS vector_sim,
            c.metadata,
            d.title AS doc_title,
            d.source AS doc_source
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.embedding IS NOT NULL
          AND (
            p_allowed_groups IS NULL
            OR d.metadata->>'allowed_group' IS NULL
            OR d.metadata->>'allowed_group' = ANY(p_allowed_groups)
          )
          AND (
            p_allowed_nextcloud_file_ids IS NULL
            OR (
                d.metadata ? 'nextcloud_file_id'
                AND d.metadata->>'nextcloud_file_id' = ANY(p_allowed_nextcloud_file_ids)
            )
          )
    ),
    text_results AS (
        SELECT
            c.id AS chunk_id,
            c.document_id,
            c.content,
            ts_rank_cd(
                to_tsvector('english', c.content),
                plainto_tsquery('english', query_text)
            )::double precision AS text_sim,
            c.metadata,
            d.title AS doc_title,
            d.source AS doc_source
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE to_tsvector('english', c.content)
              @@ plainto_tsquery('english', query_text)
          AND (
            p_allowed_groups IS NULL
            OR d.metadata->>'allowed_group' IS NULL
            OR d.metadata->>'allowed_group' = ANY(p_allowed_groups)
          )
          AND (
            p_allowed_nextcloud_file_ids IS NULL
            OR (
                d.metadata ? 'nextcloud_file_id'
                AND d.metadata->>'nextcloud_file_id' = ANY(p_allowed_nextcloud_file_ids)
            )
          )
    )
    SELECT
        COALESCE(v.chunk_id, t.chunk_id) AS chunk_id,
        COALESCE(v.document_id, t.document_id) AS document_id,
        COALESCE(v.content, t.content) AS content,
        (
            COALESCE(v.vector_sim, 0)::double precision * (1 - text_weight) +
            COALESCE(t.text_sim, 0)::double precision * text_weight
        ) AS combined_score,
        COALESCE(v.vector_sim, 0)::double precision AS vector_similarity,
        COALESCE(t.text_sim, 0)::double precision AS text_similarity,
        COALESCE(v.metadata, t.metadata) AS metadata,
        COALESCE(v.doc_title, t.doc_title) AS document_title,
        COALESCE(v.doc_source, t.doc_source) AS document_source
    FROM vector_results v
    FULL OUTER JOIN text_results t
        ON v.chunk_id = t.chunk_id
    ORDER BY combined_score DESC
    LIMIT match_count;
END;
$$;