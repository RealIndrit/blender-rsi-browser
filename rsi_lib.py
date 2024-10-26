import shutil
import threading
import typing as t
import pathlib
import json
import logging
import urllib.request
import urllib.parse
import re

log = logging.getLogger(__name__)

class RSIException(Exception):
    pass

class RSIApiWrapper:
    def __init__(self):
        self.cache_dir = pathlib.Path("./cache")
        log.debug(f"Cache dir: {self.cache_dir}")

    def clear_cache(self):
        log.debug(f"Cleared cache dir: {self.cache_dir}")
        shutil.rmtree(self.cache_dir)

    def _get(
        self,
        url: str,
        params: t.Dict[str, str] = {},
        headers: t.Dict[str, str] = {},
    ) -> str:
        headers['user-agent'] = "RSIBrowser"
        try:
            url_ = url + "?" + urllib.parse.urlencode(params)
            log.debug(f"URL: {url_}")
            return urllib.request.urlopen(
                urllib.request.Request(
                    url_, headers=headers
                )
            ).read()
        except Exception as e:
            log.exception(f"Error fetching {url}:")
            raise RSIException(f"Error fetching {url}: {e}")

    def _post(self,
            url: str,
            headers: t.Dict[str, str] = {},
            data: bytes = None,
    ) -> str:
        headers['user-agent'] = "RSIBrowser"
        try:
            return urllib.request.urlopen(
                urllib.request.Request(
                    url, headers=headers, data=data
                )
            ).read()
        except Exception as e:
            log.exception(f"Error fetching {url}:")
            raise Exception(f"Error fetching {url}: {e}")

    def _get_json(
        self,
        url: str,
        params: t.Dict[str, str] = {},
        headers: t.Dict[str, str] = {},
    ) -> t.Dict[str, t.Any]:
        return json.loads(self._get(url, params=params, headers=headers))

    def _post_json(
        self,
        url: str,
        headers: t.Dict[str, str] = {},
        data: bytes = None,
    ) -> t.Dict[str, t.Any]:
        return json.loads(self._post(url, headers=headers, data=data))

    def search(self, query: str) -> t.List[t.Dict[str, t.Any]]:
        try:
            url = f"https://robertsspaceindustries.com/graphql"
            data = ("""
            [
                {
                    "operationName": "GetShipList",
                    "variables": {
                        "query": {
                            "limit": 20,
                            "ships": {
                                "name": "SHIP_NAME"
                            }
                        }
                    },
                    "query": "query GetShipList($query: SearchQuery!) {\\n  store(name: \\"pledge\\", browse: true) {\\n    search(query: $query) {\\n      resources {\\n        ...RSIShipFragment\\n        __typename\\n      }\\n      __typename\\n    }\\n    __typename\\n  }\\n}\\n\\nfragment RSIShipFragment on RSIShip {\\n  id\\n \\n}"
                }
            ]""".replace("SHIP_NAME", query))
            headers = {"content-type": "application/json"}
            search_results = self._post_json(url, headers=headers, data=data.encode("utf-8"))

        except Exception as e:
            log.exception(f"Error searching for {query}:")
            raise RSIException(f"Error searching for {query}: {e}")

        results = []
        def fetch_ship_info(ship):
            ship_info = self.get_ship_info(ship['id'])
            results.append({
                "name": ship_info["name"],
                "id": ship_info["id"],
                "thumbnail": ship_info["media"][0]["images"]['subscribers_vault_thumbnail'],
                "url": ship_info["url"]
            })

        threads = []
        for ship in search_results[0]['data']['store']['search']['resources']:
            t = threading.Thread(target=fetch_ship_info, args=(ship,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        return results

    def get_ship_info(self, ship_id: str) -> json:
        """
        Get ship information for the given name.
        """
        log.debug(f"Getting SI for #{ship_id}")
        cache_path = self.cache_dir / ship_id / "ship_info.json"
        if not cache_path.exists():
            try:
                log.info(f"Downloading SI for #{ship_id}")
                url = f"https://robertsspaceindustries.com/ship-matrix/index"
                params = {
                    "id": ship_id
                }
                data = self._get_json(url, params=params)['data'][0]

                website_data = self._get(f'https://robertsspaceindustries.com{data["url"]}')
                pattern = r"(?P<tag>model_3d:\s*)\'(?P<model>[^\']+)"
                result = re.search(pattern, website_data.decode("utf-8"))

                if result:
                    data['hologram_3d'] = result.group('model')
                else:
                    data['hologram_3d'] = None

                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(data))
                return data
            except Exception as e:
                log.exception(f"Error downloading SI for #{ship_id}: {e}")
                raise RSIException(f"Error downloading SI for #{ship_id}: {e}")

        return json.loads(cache_path.read_text())

    def get_thumbnail(self, sid: str, url: str) -> str:
        """
        Get a thumbnail for the given ship.

        Returns the path to the downloaded thumbnail in JPEG format.
        """
        log.info(f"Getting thumbnail for #{sid}")
        cache_path = self.cache_dir / sid / "thumbnail.jpg"

        if not cache_path.exists():
            try:
                log.debug(f"Downloading thumbnail for #{sid}")

                if url.startswith("https://"):
                    data = self._get(url)
                else:
                    data = self._get(f"https://robertsspaceindustries.com{url}")

                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(data)
            except Exception as e:
                log.exception(f"Error downloading thumbnail for #{sid}:")
                raise RSIException(f"Error downloading thumbnail for #{sid}: {e}")

        return str(cache_path)

    def get_model(self, sid: str, url: str) -> str:
        """
        Get a 3D model for the given ship.

        Returns the path to the downloaded model in GLB format.
        """
        log.info(f"Getting model for #{sid}")
        cache_path = self.cache_dir / sid / "model.ctm"

        if not cache_path.exists():
            log.info(f"Downloading model for #{sid}")
            try:
                log.debug(f"Trying to download model for #{sid}")
                if url is not None:

                    if url.startswith("https://"):
                        data = self._get(url)
                    else:
                        data = self._get(f"https://robertsspaceindustries.com{url}")

                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_bytes(data)
                    log.debug(f"Cache for model #{sid} at path #{cache_path}")
                else:
                    log.debug(f"Model for #{sid} could not be downloaded")
            except Exception as e:
                log.exception(f"Error downloading model for #{sid}:")
                raise RSIException(f"Error downloading model for #{sid}: {e}")

        return str(cache_path)

    if __name__ == "__main__":
        logging.basicConfig(
            level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )