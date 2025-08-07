#!/bin/bash

echo "Checking Redis..."
pgrep -f redis-server > /dev/null || echo "Redis is not running"

echo "Checking Kafka REST..."
pgrep -f kafka-rest > /dev/null || echo "Kafka REST is not running"

echo "Checking Kafka Connect..."
pgrep -f start_kafka_connect.sh > /dev/null || echo "Kafka Connect is not running"

echo "Checking StepTimerWebsocket..."
pgrep -f StepTimerWebsocket-1.0-SNAPSHOT.jar > /dev/null || echo "StepTimerWebsocket is not running"
