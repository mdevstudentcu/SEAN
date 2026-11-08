#pragma once
// MESSAGE PNT_IMU_RAW PACKING

#include <stdint.h>

#define MAVLINK_MSG_ID_PNT_IMU_RAW 61002


typedef struct __mavlink_pnt_imu_raw_t {
 uint64_t time_us; /*<  Hub monotonic time.*/
 float accel[3]; /*<  m/s^2*/
 float gyro[3]; /*<  rad/s*/
 float temp; /*<  degC*/
} mavlink_pnt_imu_raw_t;

#define MAVLINK_MSG_ID_PNT_IMU_RAW_LEN 36
#define MAVLINK_MSG_ID_PNT_IMU_RAW_MIN_LEN 36
#define MAVLINK_MSG_ID_61002_LEN 36
#define MAVLINK_MSG_ID_61002_MIN_LEN 36

#define MAVLINK_MSG_ID_PNT_IMU_RAW_CRC 37
#define MAVLINK_MSG_ID_61002_CRC 37

#define MAVLINK_MSG_PNT_IMU_RAW_FIELD_ACCEL_LEN 3
#define MAVLINK_MSG_PNT_IMU_RAW_FIELD_GYRO_LEN 3

#if MAVLINK_COMMAND_24BIT
#define MAVLINK_MESSAGE_INFO_PNT_IMU_RAW { \
    61002, \
    "PNT_IMU_RAW", \
    4, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_imu_raw_t, time_us) }, \
         { "accel", NULL, MAVLINK_TYPE_FLOAT, 3, 8, offsetof(mavlink_pnt_imu_raw_t, accel) }, \
         { "gyro", NULL, MAVLINK_TYPE_FLOAT, 3, 20, offsetof(mavlink_pnt_imu_raw_t, gyro) }, \
         { "temp", NULL, MAVLINK_TYPE_FLOAT, 0, 32, offsetof(mavlink_pnt_imu_raw_t, temp) }, \
         } \
}
#else
#define MAVLINK_MESSAGE_INFO_PNT_IMU_RAW { \
    "PNT_IMU_RAW", \
    4, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_imu_raw_t, time_us) }, \
         { "accel", NULL, MAVLINK_TYPE_FLOAT, 3, 8, offsetof(mavlink_pnt_imu_raw_t, accel) }, \
         { "gyro", NULL, MAVLINK_TYPE_FLOAT, 3, 20, offsetof(mavlink_pnt_imu_raw_t, gyro) }, \
         { "temp", NULL, MAVLINK_TYPE_FLOAT, 0, 32, offsetof(mavlink_pnt_imu_raw_t, temp) }, \
         } \
}
#endif

/**
 * @brief Pack a pnt_imu_raw message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time.
 * @param accel  m/s^2
 * @param gyro  rad/s
 * @param temp  degC
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_imu_raw_pack(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg,
                               uint64_t time_us, const float *accel, const float *gyro, float temp)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_IMU_RAW_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 32, temp);
    _mav_put_float_array(buf, 8, accel, 3);
    _mav_put_float_array(buf, 20, gyro, 3);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN);
#else
    mavlink_pnt_imu_raw_t packet;
    packet.time_us = time_us;
    packet.temp = temp;
    mav_array_memcpy(packet.accel, accel, sizeof(float)*3);
    mav_array_memcpy(packet.gyro, gyro, sizeof(float)*3);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_IMU_RAW;
    return mavlink_finalize_message(msg, system_id, component_id, MAVLINK_MSG_ID_PNT_IMU_RAW_MIN_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_CRC);
}

/**
 * @brief Pack a pnt_imu_raw message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time.
 * @param accel  m/s^2
 * @param gyro  rad/s
 * @param temp  degC
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_imu_raw_pack_status(uint8_t system_id, uint8_t component_id, mavlink_status_t *_status, mavlink_message_t* msg,
                               uint64_t time_us, const float *accel, const float *gyro, float temp)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_IMU_RAW_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 32, temp);
    _mav_put_float_array(buf, 8, accel, 3);
    _mav_put_float_array(buf, 20, gyro, 3);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN);
#else
    mavlink_pnt_imu_raw_t packet;
    packet.time_us = time_us;
    packet.temp = temp;
    mav_array_memcpy(packet.accel, accel, sizeof(float)*3);
    mav_array_memcpy(packet.gyro, gyro, sizeof(float)*3);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_IMU_RAW;
#if MAVLINK_CRC_EXTRA
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_IMU_RAW_MIN_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_CRC);
#else
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_IMU_RAW_MIN_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN);
#endif
}

/**
 * @brief Pack a pnt_imu_raw message on a channel
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param time_us  Hub monotonic time.
 * @param accel  m/s^2
 * @param gyro  rad/s
 * @param temp  degC
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_imu_raw_pack_chan(uint8_t system_id, uint8_t component_id, uint8_t chan,
                               mavlink_message_t* msg,
                                   uint64_t time_us,const float *accel,const float *gyro,float temp)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_IMU_RAW_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 32, temp);
    _mav_put_float_array(buf, 8, accel, 3);
    _mav_put_float_array(buf, 20, gyro, 3);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN);
#else
    mavlink_pnt_imu_raw_t packet;
    packet.time_us = time_us;
    packet.temp = temp;
    mav_array_memcpy(packet.accel, accel, sizeof(float)*3);
    mav_array_memcpy(packet.gyro, gyro, sizeof(float)*3);
        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_IMU_RAW;
    return mavlink_finalize_message_chan(msg, system_id, component_id, chan, MAVLINK_MSG_ID_PNT_IMU_RAW_MIN_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_CRC);
}

/**
 * @brief Encode a pnt_imu_raw struct
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 * @param pnt_imu_raw C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_imu_raw_encode(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg, const mavlink_pnt_imu_raw_t* pnt_imu_raw)
{
    return mavlink_msg_pnt_imu_raw_pack(system_id, component_id, msg, pnt_imu_raw->time_us, pnt_imu_raw->accel, pnt_imu_raw->gyro, pnt_imu_raw->temp);
}

/**
 * @brief Encode a pnt_imu_raw struct on a channel
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param pnt_imu_raw C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_imu_raw_encode_chan(uint8_t system_id, uint8_t component_id, uint8_t chan, mavlink_message_t* msg, const mavlink_pnt_imu_raw_t* pnt_imu_raw)
{
    return mavlink_msg_pnt_imu_raw_pack_chan(system_id, component_id, chan, msg, pnt_imu_raw->time_us, pnt_imu_raw->accel, pnt_imu_raw->gyro, pnt_imu_raw->temp);
}

/**
 * @brief Encode a pnt_imu_raw struct with provided status structure
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 * @param pnt_imu_raw C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_imu_raw_encode_status(uint8_t system_id, uint8_t component_id, mavlink_status_t* _status, mavlink_message_t* msg, const mavlink_pnt_imu_raw_t* pnt_imu_raw)
{
    return mavlink_msg_pnt_imu_raw_pack_status(system_id, component_id, _status, msg,  pnt_imu_raw->time_us, pnt_imu_raw->accel, pnt_imu_raw->gyro, pnt_imu_raw->temp);
}

/**
 * @brief Send a pnt_imu_raw message
 * @param chan MAVLink channel to send the message
 *
 * @param time_us  Hub monotonic time.
 * @param accel  m/s^2
 * @param gyro  rad/s
 * @param temp  degC
 */
#ifdef MAVLINK_USE_CONVENIENCE_FUNCTIONS

static inline void mavlink_msg_pnt_imu_raw_send(mavlink_channel_t chan, uint64_t time_us, const float *accel, const float *gyro, float temp)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_IMU_RAW_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 32, temp);
    _mav_put_float_array(buf, 8, accel, 3);
    _mav_put_float_array(buf, 20, gyro, 3);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_IMU_RAW, buf, MAVLINK_MSG_ID_PNT_IMU_RAW_MIN_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_CRC);
#else
    mavlink_pnt_imu_raw_t packet;
    packet.time_us = time_us;
    packet.temp = temp;
    mav_array_memcpy(packet.accel, accel, sizeof(float)*3);
    mav_array_memcpy(packet.gyro, gyro, sizeof(float)*3);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_IMU_RAW, (const char *)&packet, MAVLINK_MSG_ID_PNT_IMU_RAW_MIN_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_CRC);
#endif
}

/**
 * @brief Send a pnt_imu_raw message
 * @param chan MAVLink channel to send the message
 * @param struct The MAVLink struct to serialize
 */
static inline void mavlink_msg_pnt_imu_raw_send_struct(mavlink_channel_t chan, const mavlink_pnt_imu_raw_t* pnt_imu_raw)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    mavlink_msg_pnt_imu_raw_send(chan, pnt_imu_raw->time_us, pnt_imu_raw->accel, pnt_imu_raw->gyro, pnt_imu_raw->temp);
#else
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_IMU_RAW, (const char *)pnt_imu_raw, MAVLINK_MSG_ID_PNT_IMU_RAW_MIN_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_CRC);
#endif
}

#if MAVLINK_MSG_ID_PNT_IMU_RAW_LEN <= MAVLINK_MAX_PAYLOAD_LEN
/*
  This variant of _send() can be used to save stack space by reusing
  memory from the receive buffer.  The caller provides a
  mavlink_message_t which is the size of a full mavlink message. This
  is usually the receive buffer for the channel, and allows a reply to an
  incoming message with minimum stack space usage.
 */
static inline void mavlink_msg_pnt_imu_raw_send_buf(mavlink_message_t *msgbuf, mavlink_channel_t chan,  uint64_t time_us, const float *accel, const float *gyro, float temp)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char *buf = (char *)msgbuf;
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 32, temp);
    _mav_put_float_array(buf, 8, accel, 3);
    _mav_put_float_array(buf, 20, gyro, 3);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_IMU_RAW, buf, MAVLINK_MSG_ID_PNT_IMU_RAW_MIN_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_CRC);
#else
    mavlink_pnt_imu_raw_t *packet = (mavlink_pnt_imu_raw_t *)msgbuf;
    packet->time_us = time_us;
    packet->temp = temp;
    mav_array_memcpy(packet->accel, accel, sizeof(float)*3);
    mav_array_memcpy(packet->gyro, gyro, sizeof(float)*3);
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_IMU_RAW, (const char *)packet, MAVLINK_MSG_ID_PNT_IMU_RAW_MIN_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN, MAVLINK_MSG_ID_PNT_IMU_RAW_CRC);
#endif
}
#endif

#endif

// MESSAGE PNT_IMU_RAW UNPACKING


/**
 * @brief Get field time_us from pnt_imu_raw message
 *
 * @return  Hub monotonic time.
 */
static inline uint64_t mavlink_msg_pnt_imu_raw_get_time_us(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint64_t(msg,  0);
}

/**
 * @brief Get field accel from pnt_imu_raw message
 *
 * @return  m/s^2
 */
static inline uint16_t mavlink_msg_pnt_imu_raw_get_accel(const mavlink_message_t* msg, float *accel)
{
    return _MAV_RETURN_float_array(msg, accel, 3,  8);
}

/**
 * @brief Get field gyro from pnt_imu_raw message
 *
 * @return  rad/s
 */
static inline uint16_t mavlink_msg_pnt_imu_raw_get_gyro(const mavlink_message_t* msg, float *gyro)
{
    return _MAV_RETURN_float_array(msg, gyro, 3,  20);
}

/**
 * @brief Get field temp from pnt_imu_raw message
 *
 * @return  degC
 */
static inline float mavlink_msg_pnt_imu_raw_get_temp(const mavlink_message_t* msg)
{
    return _MAV_RETURN_float(msg,  32);
}

/**
 * @brief Decode a pnt_imu_raw message into a struct
 *
 * @param msg The message to decode
 * @param pnt_imu_raw C-struct to decode the message contents into
 */
static inline void mavlink_msg_pnt_imu_raw_decode(const mavlink_message_t* msg, mavlink_pnt_imu_raw_t* pnt_imu_raw)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    pnt_imu_raw->time_us = mavlink_msg_pnt_imu_raw_get_time_us(msg);
    mavlink_msg_pnt_imu_raw_get_accel(msg, pnt_imu_raw->accel);
    mavlink_msg_pnt_imu_raw_get_gyro(msg, pnt_imu_raw->gyro);
    pnt_imu_raw->temp = mavlink_msg_pnt_imu_raw_get_temp(msg);
#else
        uint8_t len = msg->len < MAVLINK_MSG_ID_PNT_IMU_RAW_LEN? msg->len : MAVLINK_MSG_ID_PNT_IMU_RAW_LEN;
        memset(pnt_imu_raw, 0, MAVLINK_MSG_ID_PNT_IMU_RAW_LEN);
    memcpy(pnt_imu_raw, _MAV_PAYLOAD(msg), len);
#endif
}
