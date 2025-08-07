from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col
from pyspark.sql.types import StructType, StructField, StringType, DoubleType

# Define schema for stedi-events JSON (not base64 encoded)
customer_risk_schema = StructType([
    StructField("customer", StringType()),
    StructField("score", DoubleType()),
    StructField("riskDate", StringType())
])

# Create Spark session
spark = SparkSession.builder \
    .appName("KafkaStediEventsStream") \
    .getOrCreate()

# Set log level to WARN
spark.sparkContext.setLogLevel("WARN")

# Read from Kafka topic stedi-events
stedi_raw_stream_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "stedi-events") \
    .option("startingOffsets", "earliest") \
    .load()

# Cast Kafka 'value' to STRING
stedi_stream_df = stedi_raw_stream_df.selectExpr("CAST(value AS STRING) as value")

# Parse JSON from the value column
stedi_parsed_df = stedi_stream_df \
    .withColumn("stediData", from_json(col("value"), customer_risk_schema)) \
    .select("stediData.*")

# Create a temporary view
stedi_parsed_df.createOrReplaceTempView("CustomerRisk")

# Query to get customer and score
customerRiskStreamingDF = spark.sql("""
    SELECT customer, score
    FROM CustomerRisk
    WHERE customer IS NOT NULL AND score IS NOT NULL
""")

# Sink to console
query = customerRiskStreamingDF.writeStream \
    .outputMode("append") \
    .format("console") \
    .option("truncate", False) \
    .start()

query.awaitTermination()
