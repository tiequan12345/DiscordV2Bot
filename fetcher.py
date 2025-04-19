import requests
import datetime
import asyncio

async def fetch_and_process_channel_data(channel_ids, hours, user_token):
    print(f"Fetching data for {len(channel_ids)} channels...")

    all_messages_data = []
    channel_names = {}
    total_messages_found = 0

    headers = {}
    if user_token:
        headers = {
            'Authorization': user_token,
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'
        }

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)

    async def _fetch_channel_info(channel_id):
        if not user_token:
            return {'name': f'Unknown-{channel_id}'}
        url = f"https://discord.com/api/v9/channels/{channel_id}"
        try:
            resp = await asyncio.to_thread(requests.get, url, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            else:
                return {'name': f'Error-{channel_id}'}
        except:
            return {'name': f'Error-{channel_id}'}

    async def _fetch_messages(channel_id):
        if not user_token:
            return []
        messages_list = []
        last_id = None
        while True:
            url = f"https://discord.com/api/v9/channels/{channel_id}/messages?limit=100"
            if last_id:
                url += f"&before={last_id}"
            try:
                resp = await asyncio.to_thread(requests.get, url, headers=headers)
                if resp.status_code != 200:
                    break
                msgs = resp.json()
                if not msgs:
                    break
                page_msgs = []
                hit_cutoff = False
                for msg in msgs:
                    ts = msg.get('timestamp')
                    if not ts:
                        continue
                    msg_time = datetime.datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    if msg_time > cutoff:
                        page_msgs.append(msg)
                    else:
                        hit_cutoff = True
                messages_list.extend(page_msgs)
                if hit_cutoff:
                    break
                last_id = msgs[-1]['id']
                await asyncio.sleep(0.5)
            except:
                break
        return [
            m for m in messages_list
            if datetime.datetime.fromisoformat(m['timestamp'].replace('Z', '+00:00')) > cutoff
        ]

    fetch_tasks = []
    channel_tasks = {}

    for cid in channel_ids:
        info_task = asyncio.create_task(_fetch_channel_info(cid))
        msg_task = asyncio.create_task(_fetch_messages(cid))
        fetch_tasks.append(msg_task)
        channel_tasks[cid] = (info_task, msg_task)

    await asyncio.gather(*fetch_tasks)

    for cid, (info_task, msg_task) in channel_tasks.items():
        info = await info_task
        name = info.get('name', f'Unknown-{cid}')
        channel_names[cid] = name
        msgs = msg_task.result()
        total_messages_found += len(msgs)
        for m in msgs:
            author = m.get('author', {}).get('global_name') or m.get('author', {}).get('username', 'Unknown')
            all_messages_data.append({
                'channel': name,
                'author': author,
                'content': m.get('content'),
                'timestamp': m.get('timestamp')
            })

    all_messages_data.sort(key=lambda x: x.get('timestamp', ''))
    return all_messages_data, channel_names, total_messages_found