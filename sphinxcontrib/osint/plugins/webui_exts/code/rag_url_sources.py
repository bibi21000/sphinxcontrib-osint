"""
title: Add RAG URL Sources
description: Inject RAG URLs into sources
author: bibi21000
version: 1.0
type: filter
"""
from typing import Dict, Any

async def outlet(
    response: Dict[str, Any],
    context: Dict[str, Any],
    **kwargs
) -> Dict[str, Any]:

    documents = context.get('documents', [])
    sources = []
    seen = set()

    for doc in documents:
        metadata = doc.get('metadata', {})
        data = metadata.get('data', {})
        url = data.get('src_url')

        if url and url not in seen:
            seen.add(url)
            sources.append({
                'type': 'url',
                'url': url,
                'title': data.get('title', url)
            })

    if sources:
        response.setdefault('sources', [])
        response['sources'].extend(sources)

    return response


