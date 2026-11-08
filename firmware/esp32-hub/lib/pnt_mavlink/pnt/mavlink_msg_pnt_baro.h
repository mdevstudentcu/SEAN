#pragma once
// MESSAGE PNT_BARO PACKING

#include <stdint.h>

#define MAVLINK_MSG_ID_PNT_BARO 61003


typedef struct __mavlink_pnt_baro_t {
 uint64_t time_us; /*<  Hub monotonic time.*/
 float pressure; /*<  Pa*/
 float temp; /*<  degC*/
} mavlink_pnt_baro_t;

#define MAVLINK_MSG_ID_PNT_BARO_LEN 16
#define MAVLINK_MSG_ID_PNT_BARO_MIN_LEN 16
#define MAVLINK_MSG_ID_61003_LEN 16
#define MAVLINK_MSG_ID_61003_MIN_LEN 16

#define MAVLINK_MSG_ID_PNT_BARO_CRC 102
#define MAVLINK_MSG_ID_61003_CRC 102



#if MAVLINK_COMMAND_24BIT
#define MAVLINK_MESSAGE_INFO_PNT_BARO { \
    61003, \
    "PNT_BARO", \
    3, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_baro_t, time_us) }, \
         { "pressure", NULL, MAVLINK_TYPE_FLOAT, 0, 8, offsetof(mavlink_pnt_baro_t, pressure) }, \
         { "temp", NULL, MAVLINK_TYPE_FLOAT, 0, 12, offsetof(mavlink_pnt_baro_t, temp) }, \
         } \
}
#else
#define MAVLINK_MESSAGE_INFO_PNT_BARO { \
    "PNT_BARO", \
    3, \
    {  { "time_us", NULL, MAVLINK_TYPE_UINT64_T, 0, 0, offsetof(mavlink_pnt_baro_t, time_us) }, \
         { "pressure", NULL, MAVLINK_TYPE_FLOAT, 0, 8, offsetof(mavlink_pnt_baro_t, pressure) }, \
         { "temp", NULL, MAVLINK_TYPE_FLOAT, 0, 12, offsetof(mavlink_pnt_baro_t, temp) }, \
         } \
}
#endif

/**
 * @brief Pack a pnt_baro message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time.
 * @param pressure  Pa
 * @param temp  degC
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_baro_pack(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg,
                               uint64_t time_us, float pressure, float temp)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_BARO_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 8, pressure);
    _mav_put_float(buf, 12, temp);

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_BARO_LEN);
#else
    mavlink_pnt_baro_t packet;
    packet.time_us = time_us;
    packet.pressure = pressure;
    packet.temp = temp;

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_BARO_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_BARO;
    return mavlink_finalize_message(msg, system_id, component_id, MAVLINK_MSG_ID_PNT_BARO_MIN_LEN, MAVLINK_MSG_ID_PNT_BARO_LEN, MAVLINK_MSG_ID_PNT_BARO_CRC);
}

/**
 * @brief Pack a pnt_baro message
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 *
 * @param time_us  Hub monotonic time.
 * @param pressure  Pa
 * @param temp  degC
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_baro_pack_status(uint8_t system_id, uint8_t component_id, mavlink_status_t *_status, mavlink_message_t* msg,
                               uint64_t time_us, float pressure, float temp)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_BARO_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 8, pressure);
    _mav_put_float(buf, 12, temp);

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_BARO_LEN);
#else
    mavlink_pnt_baro_t packet;
    packet.time_us = time_us;
    packet.pressure = pressure;
    packet.temp = temp;

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_BARO_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_BARO;
#if MAVLINK_CRC_EXTRA
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_BARO_MIN_LEN, MAVLINK_MSG_ID_PNT_BARO_LEN, MAVLINK_MSG_ID_PNT_BARO_CRC);
#else
    return mavlink_finalize_message_buffer(msg, system_id, component_id, _status, MAVLINK_MSG_ID_PNT_BARO_MIN_LEN, MAVLINK_MSG_ID_PNT_BARO_LEN);
#endif
}

/**
 * @brief Pack a pnt_baro message on a channel
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param time_us  Hub monotonic time.
 * @param pressure  Pa
 * @param temp  degC
 * @return length of the message in bytes (excluding serial stream start sign)
 */
static inline uint16_t mavlink_msg_pnt_baro_pack_chan(uint8_t system_id, uint8_t component_id, uint8_t chan,
                               mavlink_message_t* msg,
                                   uint64_t time_us,float pressure,float temp)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_BARO_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 8, pressure);
    _mav_put_float(buf, 12, temp);

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), buf, MAVLINK_MSG_ID_PNT_BARO_LEN);
#else
    mavlink_pnt_baro_t packet;
    packet.time_us = time_us;
    packet.pressure = pressure;
    packet.temp = temp;

        memcpy(_MAV_PAYLOAD_NON_CONST(msg), &packet, MAVLINK_MSG_ID_PNT_BARO_LEN);
#endif

    msg->msgid = MAVLINK_MSG_ID_PNT_BARO;
    return mavlink_finalize_message_chan(msg, system_id, component_id, chan, MAVLINK_MSG_ID_PNT_BARO_MIN_LEN, MAVLINK_MSG_ID_PNT_BARO_LEN, MAVLINK_MSG_ID_PNT_BARO_CRC);
}

/**
 * @brief Encode a pnt_baro struct
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param msg The MAVLink message to compress the data into
 * @param pnt_baro C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_baro_encode(uint8_t system_id, uint8_t component_id, mavlink_message_t* msg, const mavlink_pnt_baro_t* pnt_baro)
{
    return mavlink_msg_pnt_baro_pack(system_id, component_id, msg, pnt_baro->time_us, pnt_baro->pressure, pnt_baro->temp);
}

/**
 * @brief Encode a pnt_baro struct on a channel
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param chan The MAVLink channel this message will be sent over
 * @param msg The MAVLink message to compress the data into
 * @param pnt_baro C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_baro_encode_chan(uint8_t system_id, uint8_t component_id, uint8_t chan, mavlink_message_t* msg, const mavlink_pnt_baro_t* pnt_baro)
{
    return mavlink_msg_pnt_baro_pack_chan(system_id, component_id, chan, msg, pnt_baro->time_us, pnt_baro->pressure, pnt_baro->temp);
}

/**
 * @brief Encode a pnt_baro struct with provided status structure
 *
 * @param system_id ID of this system
 * @param component_id ID of this component (e.g. 200 for IMU)
 * @param status MAVLink status structure
 * @param msg The MAVLink message to compress the data into
 * @param pnt_baro C-struct to read the message contents from
 */
static inline uint16_t mavlink_msg_pnt_baro_encode_status(uint8_t system_id, uint8_t component_id, mavlink_status_t* _status, mavlink_message_t* msg, const mavlink_pnt_baro_t* pnt_baro)
{
    return mavlink_msg_pnt_baro_pack_status(system_id, component_id, _status, msg,  pnt_baro->time_us, pnt_baro->pressure, pnt_baro->temp);
}

/**
 * @brief Send a pnt_baro message
 * @param chan MAVLink channel to send the message
 *
 * @param time_us  Hub monotonic time.
 * @param pressure  Pa
 * @param temp  degC
 */
#ifdef MAVLINK_USE_CONVENIENCE_FUNCTIONS

static inline void mavlink_msg_pnt_baro_send(mavlink_channel_t chan, uint64_t time_us, float pressure, float temp)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char buf[MAVLINK_MSG_ID_PNT_BARO_LEN];
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 8, pressure);
    _mav_put_float(buf, 12, temp);

    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_BARO, buf, MAVLINK_MSG_ID_PNT_BARO_MIN_LEN, MAVLINK_MSG_ID_PNT_BARO_LEN, MAVLINK_MSG_ID_PNT_BARO_CRC);
#else
    mavlink_pnt_baro_t packet;
    packet.time_us = time_us;
    packet.pressure = pressure;
    packet.temp = temp;

    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_BARO, (const char *)&packet, MAVLINK_MSG_ID_PNT_BARO_MIN_LEN, MAVLINK_MSG_ID_PNT_BARO_LEN, MAVLINK_MSG_ID_PNT_BARO_CRC);
#endif
}

/**
 * @brief Send a pnt_baro message
 * @param chan MAVLink channel to send the message
 * @param struct The MAVLink struct to serialize
 */
static inline void mavlink_msg_pnt_baro_send_struct(mavlink_channel_t chan, const mavlink_pnt_baro_t* pnt_baro)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    mavlink_msg_pnt_baro_send(chan, pnt_baro->time_us, pnt_baro->pressure, pnt_baro->temp);
#else
    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_BARO, (const char *)pnt_baro, MAVLINK_MSG_ID_PNT_BARO_MIN_LEN, MAVLINK_MSG_ID_PNT_BARO_LEN, MAVLINK_MSG_ID_PNT_BARO_CRC);
#endif
}

#if MAVLINK_MSG_ID_PNT_BARO_LEN <= MAVLINK_MAX_PAYLOAD_LEN
/*
  This variant of _send() can be used to save stack space by reusing
  memory from the receive buffer.  The caller provides a
  mavlink_message_t which is the size of a full mavlink message. This
  is usually the receive buffer for the channel, and allows a reply to an
  incoming message with minimum stack space usage.
 */
static inline void mavlink_msg_pnt_baro_send_buf(mavlink_message_t *msgbuf, mavlink_channel_t chan,  uint64_t time_us, float pressure, float temp)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    char *buf = (char *)msgbuf;
    _mav_put_uint64_t(buf, 0, time_us);
    _mav_put_float(buf, 8, pressure);
    _mav_put_float(buf, 12, temp);

    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_BARO, buf, MAVLINK_MSG_ID_PNT_BARO_MIN_LEN, MAVLINK_MSG_ID_PNT_BARO_LEN, MAVLINK_MSG_ID_PNT_BARO_CRC);
#else
    mavlink_pnt_baro_t *packet = (mavlink_pnt_baro_t *)msgbuf;
    packet->time_us = time_us;
    packet->pressure = pressure;
    packet->temp = temp;

    _mav_finalize_message_chan_send(chan, MAVLINK_MSG_ID_PNT_BARO, (const char *)packet, MAVLINK_MSG_ID_PNT_BARO_MIN_LEN, MAVLINK_MSG_ID_PNT_BARO_LEN, MAVLINK_MSG_ID_PNT_BARO_CRC);
#endif
}
#endif

#endif

// MESSAGE PNT_BARO UNPACKING


/**
 * @brief Get field time_us from pnt_baro message
 *
 * @return  Hub monotonic time.
 */
static inline uint64_t mavlink_msg_pnt_baro_get_time_us(const mavlink_message_t* msg)
{
    return _MAV_RETURN_uint64_t(msg,  0);
}

/**
 * @brief Get field pressure from pnt_baro message
 *
 * @return  Pa
 */
static inline float mavlink_msg_pnt_baro_get_pressure(const mavlink_message_t* msg)
{
    return _MAV_RETURN_float(msg,  8);
}

/**
 * @brief Get field temp from pnt_baro message
 *
 * @return  degC
 */
static inline float mavlink_msg_pnt_baro_get_temp(const mavlink_message_t* msg)
{
    return _MAV_RETURN_float(msg,  12);
}

/**
 * @brief Decode a pnt_baro message into a struct
 *
 * @param msg The message to decode
 * @param pnt_baro C-struct to decode the message contents into
 */
static inline void mavlink_msg_pnt_baro_decode(const mavlink_message_t* msg, mavlink_pnt_baro_t* pnt_baro)
{
#if MAVLINK_NEED_BYTE_SWAP || !MAVLINK_ALIGNED_FIELDS
    pnt_baro->time_us = mavlink_msg_pnt_baro_get_time_us(msg);
    pnt_baro->pressure = mavlink_msg_pnt_baro_get_pressure(msg);
    pnt_baro->temp = mavlink_msg_pnt_baro_get_temp(msg);
#else
        uint8_t len = msg->len < MAVLINK_MSG_ID_PNT_BARO_LEN? msg->len : MAVLINK_MSG_ID_PNT_BARO_LEN;
        memset(pnt_baro, 0, MAVLINK_MSG_ID_PNT_BARO_LEN);
    memcpy(pnt_baro, _MAV_PAYLOAD(msg), len);
#endif
}
