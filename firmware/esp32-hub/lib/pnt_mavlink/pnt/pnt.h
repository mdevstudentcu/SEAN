/** @file
 *  @brief MAVLink comm protocol generated from pnt.xml
 *  @see http://mavlink.org
 */
#pragma once
#ifndef MAVLINK_PNT_H
#define MAVLINK_PNT_H

#ifndef MAVLINK_H
    #error Wrong include order: MAVLINK_PNT.H MUST NOT BE DIRECTLY USED. Include mavlink.h from the same directory instead or set ALL AND EVERY defines from MAVLINK.H manually accordingly, including the #define MAVLINK_H call.
#endif

#define MAVLINK_PNT_XML_HASH -2504827124853874527

#ifdef __cplusplus
extern "C" {
#endif

// MESSAGE LENGTHS AND CRCS

#ifndef MAVLINK_MESSAGE_LENGTHS
#define MAVLINK_MESSAGE_LENGTHS {}
#endif

#ifndef MAVLINK_MESSAGE_CRCS
#define MAVLINK_MESSAGE_CRCS {{61000, 57, 17, 17, 0, 0, 0}, {61001, 100, 16, 16, 0, 0, 0}, {61002, 37, 36, 36, 0, 0, 0}, {61003, 102, 16, 16, 0, 0, 0}, {61004, 173, 19, 19, 0, 0, 0}, {61005, 186, 25, 25, 0, 0, 0}, {61006, 219, 104, 104, 0, 0, 0}}
#endif

#include "../protocol.h"

#define MAVLINK_ENABLED_PNT

// ENUM DEFINITIONS



// MAVLINK VERSION

#ifndef MAVLINK_VERSION
#define MAVLINK_VERSION 1
#endif

#if (MAVLINK_VERSION == 0)
#undef MAVLINK_VERSION
#define MAVLINK_VERSION 1
#endif

// MESSAGE DEFINITIONS
#include "./mavlink_msg_pnt_hub_status.h"
#include "./mavlink_msg_pnt_pps.h"
#include "./mavlink_msg_pnt_imu_raw.h"
#include "./mavlink_msg_pnt_baro.h"
#include "./mavlink_msg_pnt_wifi_ap.h"
#include "./mavlink_msg_pnt_ftm_range.h"
#include "./mavlink_msg_pnt_gnss_raw_nmea.h"

// base include



#if MAVLINK_PNT_XML_HASH == MAVLINK_PRIMARY_XML_HASH
# define MAVLINK_MESSAGE_INFO {MAVLINK_MESSAGE_INFO_PNT_HUB_STATUS, MAVLINK_MESSAGE_INFO_PNT_PPS, MAVLINK_MESSAGE_INFO_PNT_IMU_RAW, MAVLINK_MESSAGE_INFO_PNT_BARO, MAVLINK_MESSAGE_INFO_PNT_WIFI_AP, MAVLINK_MESSAGE_INFO_PNT_FTM_RANGE, MAVLINK_MESSAGE_INFO_PNT_GNSS_RAW_NMEA}
# define MAVLINK_MESSAGE_NAMES {{ "PNT_BARO", 61003 }, { "PNT_FTM_RANGE", 61005 }, { "PNT_GNSS_RAW_NMEA", 61006 }, { "PNT_HUB_STATUS", 61000 }, { "PNT_IMU_RAW", 61002 }, { "PNT_PPS", 61001 }, { "PNT_WIFI_AP", 61004 }}
# if MAVLINK_COMMAND_24BIT
#  include "../mavlink_get_info.h"
# endif
#endif

#ifdef __cplusplus
}
#endif // __cplusplus
#endif // MAVLINK_PNT_H
