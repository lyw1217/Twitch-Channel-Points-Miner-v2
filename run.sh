#docker run --name user1-v $(pwd)/user1.py:/usr/src/app/run.py:ro -p 5001:5000 tkdalex/twitch-channel-points-miner-v2

#docker run --name user1-v $(pwd)/user2.py:/usr/src/app/run.py:ro -p 5001:5000 tkdalex/twitch-channel-points-miner-v2

#docker run \
#    -it \
#    -v $(pwd)/analytics:/usr/src/app/analytics \
#    -v $(pwd)/cookies:/usr/src/app/cookies \
#    -v $(pwd)/logs:/usr/src/app/logs \
#    -v $(pwd)/run.py:/usr/src/app/run.py:ro \
#    -p 5000:5000 \
#    lyw1217/twitch:latest
echo "docker stop"
docker stop twich1 twich2 twich3 twich4
echo "end"
echo
echo "docker rm"
docker rm twich1 twich2 twich3 twich4
echo "end"
echo

echo "docker run"
docker run \
    -d \
    -v $(pwd)/analytics:/usr/src/app/analytics \
    -v $(pwd)/cookies:/usr/src/app/cookies \
    -v $(pwd)/logs:/usr/src/app/logs \
    -v $(pwd)/user1.py:/usr/src/app/run.py:ro \
    --name twich1 \
    -e TZ=Asia/Seoul \
    lyw1217/twitch-channel-points-miner-v2:latest

echo "start 1"
echo

docker run \
    -d \
    -v $(pwd)/analytics:/usr/src/app/analytics \
    -v $(pwd)/cookies:/usr/src/app/cookies \
    -v $(pwd)/logs:/usr/src/app/logs \
    -v $(pwd)/user2.py:/usr/src/app/run.py:ro \
    --name twich2 \
    -e TZ=Asia/Seoul \
    lyw1217/twitch-channel-points-miner-v2:latest

echo "start 2"
echo

docker run \
    -d \
    -v $(pwd)/analytics:/usr/src/app/analytics \
    -v $(pwd)/cookies:/usr/src/app/cookies \
    -v $(pwd)/logs:/usr/src/app/logs \
    -v $(pwd)/user3.py:/usr/src/app/run.py:ro \
    --name twich3 \
    -e TZ=Asia/Seoul \
    lyw1217/twitch-channel-points-miner-v2:latest

echo "start 3"
echo

docker run \
    -d \
    -v $(pwd)/analytics:/usr/src/app/analytics \
    -v $(pwd)/cookies:/usr/src/app/cookies \
    -v $(pwd)/logs:/usr/src/app/logs \
    -v $(pwd)/user4.py:/usr/src/app/run.py:ro \
    --name twich4 \
    -e TZ=Asia/Seoul \
    lyw1217/twitch-channel-points-miner-v2:latest

echo "start 4"
echo