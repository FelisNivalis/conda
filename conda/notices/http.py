# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Sequence, Tuple, Optional

import requests

from ..common.io import Spinner
from ..gateways.connection.session import CondaSession

from .cache import cached_response
from .types import ChannelNoticeResponse

logger = logging.getLogger(__name__)


def get_notice_responses(
    url_and_names: Sequence[Tuple[str, str]], silent: bool = False, max_workers: int = 10
) -> Sequence[ChannelNoticeResponse]:
    """
    Provided a list of channel notification url/name tuples, return a sequence of
    ChannelNoticeResponse objects.

    Args:
        silent: turn off "loading animation" (defaults to False)
        max_workers: increase worker number in thread executor (defaults to 10)
    Returns:
        Sequence[ChannelNoticeResponse]
    """
    executor = ThreadPoolExecutor(max_workers=max_workers)

    with Spinner("Retrieving notices", enabled=not silent):
        return tuple(
            filter(
                None,
                (
                    chn_info
                    for chn_info in executor.map(
                        lambda args: get_channel_notice_response(*args), url_and_names
                    )
                ),
            )
        )


@cached_response
def get_channel_notice_response(url: str, name: str) -> Optional[ChannelNoticeResponse]:
    """
    Return a channel response object. We use this to wrap the response with
    additional channel information to use. If the response was invalid we suppress/log
    and error message.
    """
    session = CondaSession()
    try:
        resp = session.get(url, allow_redirects=False, timeout=5)  # timeout: connect, read
    except requests.exceptions.Timeout:
        logger.info(f"Request timed out for channel: {name} url: {url}")
        return

    try:
        if resp.status_code < 300:
            return ChannelNoticeResponse(url, name, json_data=resp.json())
        else:
            logger.info(f"Received {resp.status_code} when trying to GET {url}")
    except ValueError:
        logger.info(f"Unable to parse JSON data for {url}")
        return ChannelNoticeResponse(url, name, json_data=None)
